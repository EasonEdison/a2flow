"""Explicit owner-scoped follow-up tasks and durable business dispatch receipts.

This repository never resolves business cases from model prose or reminder reads.
A committed operation claim is dispatched once; ambiguous claims are not retried.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid
from typing import Any, Callable, Mapping, Protocol, TypedDict

from skillweave_contracts.user_id import require_user_id

from .errors import BsideError
from .interaction_continuation import continuation_reference
from .persistence_types import (
    ConnectionFactory,
    DatabaseConnection,
    DatabaseRow,
    MessageRecord,
    message_record,
)
from .work_activities import WorkActivitiesRepository


# 显式绑定处理任务、原异常、运行和会话, 不能靠最近聊天内容推测归属。
class ProcessingContext(TypedDict):
    taskId: str
    activityId: str
    runId: str
    attentionId: str
    conversationId: str
    # 处理目标和任务状态来自已保存记录, 模型只能基于该上下文继续。
    objective: str
    status: str


# 执行信封区分真实回执、重复读取与未知状态, replayed 不表示再次执行。
class OperationEnvelope(TypedDict):
    status: str
    operationId: str
    requestId: str
    replayed: bool
    result: dict[str, Any] | None
    errorCode: str | None


# 排序后的 JSON 既用于保存也用于摘要, 拒绝非标准 NaN 值。
def _json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


# 仅将时间值转换为 ISO 格式, 不改变其余业务字段。
def _time(value: object) -> object:
    return value.isoformat() if isinstance(value, dt.datetime) else value


# 将存储字段映射为运行侧固定上下文, 并保留来源异常身份。
def _context(row: Mapping[str, Any]) -> ProcessingContext:
    return {
        "taskId": row["task_id"],
        "activityId": row["activity_id"],
        "runId": row["run_id"],
        "attentionId": row["attention_id"],
        "conversationId": str(row["conversation_id"]),
        "objective": row["objective"],
        "status": row["status"],
    }


# 观察者共享消息准入事务, 只登记关系, 不调用模型或业务服务。
class ProcessingTurnObserver(Protocol):
    """Shares the admission transaction; never dispatches model or business work."""

    def __call__(
        self,
        connection: DatabaseConnection,
        context: ProcessingContext,
        input_message: MessageRecord,
        assistant_message: MessageRecord,
        *,
        new: bool,
    ) -> None: ...


# 处理仓库保存显式任务和执行回执, 不能从模型总结自动判定业务已解决。
class ProcessingTasksRepository:
    def __init__(
        self, connection_factory: ConnectionFactory, work_activities: WorkActivitiesRepository
    ) -> None:
        self._factory = connection_factory
        self._activities = work_activities

    # 统一验证用户、环境和数字会话范围, 所有查询沿用同一隔离键。
    @staticmethod
    def _scope(user_id: int, environment: str, conversation_id: str) -> tuple[int, str, int]:
        require_user_id(user_id)
        if environment not in {"PRT", "ONLINE"} or not re.fullmatch(
            r"[1-9][0-9]*", str(conversation_id)
        ):
            raise BsideError("INVALID_PROCESSING_SCOPE", 400)
        return user_id, environment, int(conversation_id)

    # 按完整范围读取任务, 写路径按需加行锁防止状态并发推进。
    @staticmethod
    def _row(
        connection: DatabaseConnection,
        scope: tuple[int, str, int],
        task_id: str,
        *,
        lock: bool = False,
    ) -> DatabaseRow:
        row = connection.execute(
            "SELECT * FROM processing_tasks WHERE user_id=%s AND environment=%s "
            "AND conversation_id=%s AND task_id=%s" + (" FOR UPDATE" if lock else ""),
            (*scope, task_id),
        ).fetchone()
        if row is None:
            raise BsideError("PROCESSING_TASK_NOT_FOUND", 404)
        return row

    # 只有当前任务绑定且尚在等待或执行的真实卡片才构成待处理交互。
    @staticmethod
    def _waiting_card(
        connection: DatabaseConnection, scope: tuple[int, str, int], task_id: str
    ) -> bool:
        return (
            connection.execute(
                "SELECT 1 FROM processing_cards p JOIN chat_a2ui_cards c ON c.user_id=p.user_id "
                "AND c.environment=p.environment AND c.conversation_id=p.conversation_id::text AND c.card_id=p.card_id "
                "WHERE p.user_id=%s AND p.environment=%s AND p.conversation_id=%s AND p.task_id=%s "
                "AND c.status IN ('WAITING_ACTION','EXECUTING') LIMIT 1",
                (*scope, task_id),
            ).fetchone()
            is not None
        )

    # 读取已有任务上下文时仍检查会话归属范围, 不能跨会话接管。
    def get_context(
        self, *, user_id: int, environment: str, conversation_id: str, task_id: str
    ) -> ProcessingContext:
        scope = self._scope(user_id, environment, conversation_id)
        with self._factory() as connection:
            return _context(self._row(connection, scope, task_id))

    def begin_turn(
        self,
        *,
        user_id: int,
        environment: str,
        conversation_id: str,
        request_id: str,
        text: str,
        references: list[dict[str, Any]],
        target: Mapping[str, str] | None = None,
        task_id: str | None = None,
        turn_observer: ProcessingTurnObserver | None = None,
    ) -> tuple[bool, ProcessingContext, MessageRecord, MessageRecord]:
        """Atomically create the user/assistant pair and explicit task relation."""
        scope = self._scope(user_id, environment, conversation_id)
        # 首次异常目标与已有任务二选一, 并要求稳定、格式合法的处理请求号。
        if bool(target) == bool(task_id) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", request_id):
            raise BsideError("INVALID_PROCESSING_REQUEST", 400)
        activity = None
        # 首次处理先从用户可见动态读取异常, 禁止凭前端传来的任意异常说明建任务。
        if target:
            activity = self._activities.get(
                user_id=user_id, environment=environment, activity_id=target["activityId"]
            )
            # 必须命中具体业务异常; 运行失败、阅读提醒等不能冒充业务处置目标。
            if not any(
                a["attentionId"] == target["attentionId"] and a["kind"] == "business"
                for a in activity["attentionItems"]
            ):
                raise BsideError("BUSINESS_ATTENTION_NOT_FOUND", 404)
        # Reference readAt is intentionally excluded: refresh must not change request identity.
        # 摘要只包含稳定输入和引用动态 ID, 读取时间变化不构成新请求。
        digest = hashlib.sha256(
            _json(
                {
                    "text": text,
                    "target": target,
                    "taskId": task_id,
                    "referenceActivities": [r.get("activityId") for r in references],
                }
            ).encode()
        ).hexdigest()
        with self._factory() as connection:
            # 锁住会话并在事务中再次验证用户, 后续消息和任务关系原子保存。
            owner = connection.execute(
                "SELECT user_id FROM conversations WHERE id=%s FOR UPDATE", (scope[2],)
            ).fetchone()
            if owner is None or owner["user_id"] != user_id:
                raise BsideError("CONVERSATION_NOT_FOUND", 404)
            # 处理请求重发先找既有轮次, 摘要不同直接报冲突。
            prior = connection.execute(
                "SELECT * FROM processing_turns WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND request_id=%s",
                (*scope, request_id),
            ).fetchone()
            if prior:
                if prior["request_digest"] != digest:
                    raise BsideError("PROCESSING_REQUEST_CONFLICT", 409)
                # 重发读取原消息对, 回调只登记客户端映射, 不再插入新待执行轮次。
                prior_rows = connection.execute(
                    "SELECT * FROM messages WHERE id IN (%s,%s) ORDER BY id",
                    (prior["input_message_id"], prior["assistant_message_id"]),
                ).fetchall()
                context = _context(self._row(connection, scope, prior["task_id"]))
                # 观察者拿到同一事务连接和 new=False, 准确区分重发与新准入。
                if turn_observer is not None:
                    turn_observer(
                        connection,
                        context,
                        message_record(prior_rows[0]),
                        message_record(prior_rows[1]),
                        new=False,
                    )
                return False, context, message_record(prior_rows[0]), message_record(prior_rows[1])
            # 首次处理建立独立任务, 目标保留用户原文及来源异常身份。
            if target:
                task_id = "handling-" + uuid.uuid4().hex
                assert activity is not None
                task = connection.execute(
                    "INSERT INTO processing_tasks "
                    "(task_id,user_id,environment,conversation_id,activity_id,run_id,attention_id,objective,status) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'OPEN') RETURNING *",
                    (
                        task_id,
                        *scope,
                        target["activityId"],
                        activity["runId"],
                        target["attentionId"],
                        text,
                    ),
                ).fetchone()
            # 继续已有任务时加锁; 已解决、失败或未知的任务不能自动继续。
            else:
                task = self._row(connection, scope, str(task_id), lock=True)
                if task["status"] in {"RESOLVED", "FAILED", "UNKNOWN"}:
                    raise BsideError("PROCESSING_TASK_NOT_CONTINUABLE", 409)
            assert task is not None
            context = _context(task)
            # 用户输入与助手占位均携带任务 ID, 历史刷新仍能找回处理关系。
            contents = [
                (
                    "user",
                    {
                        "text": text,
                        "delivery": "submitted",
                        "runReferences": references,
                        "processingTaskId": task_id,
                    },
                ),
                (
                    "assistant",
                    {"text": "", "delivery": "running", "parts": [], "processingTaskId": task_id},
                ),
            ]
            # 两条消息在同一事务插入, 避免任务只绑定其中一条。
            rows: list[MessageRecord] = []
            for role, content in contents:
                rows.append(
                    message_record(
                        connection.execute(
                            "INSERT INTO messages(conversation_id,role,content) "
                            "VALUES (%s,%s,%s::jsonb) RETURNING *",
                            (scope[2], role, _json(content)),
                        ).fetchone()
                    )
                )
            connection.execute(
                # 保存稳定处理请求号与消息对, 后续工具执行据此校验轮次归属。
                "INSERT INTO processing_turns(user_id,environment,conversation_id,request_id,"
                "request_digest,task_id,input_message_id,assistant_message_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (*scope, request_id, digest, task_id, rows[0]["id"], rows[1]["id"]),
            )
            # 仅首次消息作为任务来源消息, 继续处理不会覆盖原始入口。
            if target:
                connection.execute(
                    "UPDATE processing_tasks SET origin_message_id=%s WHERE task_id=%s",
                    (rows[0]["id"], task_id),
                )
            # 新消息回调同事务登记持久化分发轮次, 提交前不启动模型。
            if turn_observer is not None:
                turn_observer(connection, context, rows[0], rows[1], new=True)
            return True, context, rows[0], rows[1]

    # 卡片必须绑定当前任务的权威元数据, 不能仅凭 ID 建立处理关系。
    def bind_card(
        self, *, user_id: int, environment: str, conversation_id: str, task_id: str, card_id: str
    ) -> None:
        scope = self._scope(user_id, environment, conversation_id)
        if not isinstance(card_id, str) or not 1 <= len(card_id) <= 256:
            raise BsideError("INVALID_PROCESSING_CARD", 400)
        with self._factory() as connection:
            task = self._row(connection, scope, task_id, lock=True)
            if task["status"] in {"RESOLVED", "FAILED", "UNKNOWN"}:
                raise BsideError("PROCESSING_TASK_NOT_CONTINUABLE", 409)
            # 验证卡片属于同一用户、环境与会话, 再检查其中的任务 ID。
            saved_card = connection.execute(
                "SELECT status,binding_metadata FROM chat_a2ui_cards WHERE user_id=%s "
                "AND environment=%s AND conversation_id=%s AND card_id=%s",
                (user_id, environment, str(scope[2]), card_id),
            ).fetchone()
            # 缺卡片或任务不匹配直接拒绝, 不能将显示上的相邻位置视为归属。
            if (
                saved_card is None
                or saved_card["binding_metadata"].get("processingTaskId") != task_id
            ):
                raise BsideError("PROCESSING_CARD_NOT_FOUND", 404)
            connection.execute(
                "INSERT INTO processing_cards(user_id,environment,conversation_id,card_id,task_id) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (*scope, card_id, task_id),
            )
            # 插入后读回绑定, 已有卡片属于其他任务时明确报冲突。
            row = connection.execute(
                "SELECT task_id FROM processing_cards WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND card_id=%s",
                (*scope, card_id),
            ).fetchone()
            assert row is not None
            if row["task_id"] != task_id:
                raise BsideError("PROCESSING_CARD_CONFLICT", 409)
            # 等待卡片使任务进入 WAITING_INPUT, 补参结束前不宣称处理完成。
            if saved_card["status"] == "WAITING_ACTION":
                connection.execute(
                    "UPDATE processing_tasks SET status='WAITING_INPUT',updated_at=now() WHERE task_id=%s",
                    (task_id,),
                )

    # 卡片关联表与权威元数据必须一致, 缺少一侧证据不能猜测任务。
    def context_for_card(
        self, *, user_id: int, environment: str, conversation_id: str, card_id: str
    ) -> ProcessingContext | None:
        scope = self._scope(user_id, environment, conversation_id)
        with self._factory() as connection:
            row = connection.execute(
                "SELECT task_id FROM processing_cards WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND card_id=%s",
                (*scope, card_id),
            ).fetchone()
            # 同时读取卡片元数据, 识别绑定缺失和普通无处理任务卡片。
            card = connection.execute(
                "SELECT binding_metadata FROM chat_a2ui_cards WHERE user_id=%s "
                "AND environment=%s AND conversation_id=%s AND card_id=%s",
                (user_id, environment, str(scope[2]), card_id),
            ).fetchone()
            metadata_task = card["binding_metadata"].get("processingTaskId") if card else None
            # 普通卡片返回无上下文; 声明了任务却没有一致绑定则阻止恢复。
            if row is None and (card is None or "processingTaskId" not in card["binding_metadata"]):
                return None
            if row is None or not isinstance(metadata_task, str) or metadata_task != row["task_id"]:
                raise BsideError("PROCESSING_CARD_BINDING_UNCONFIRMED", 409)
            return _context(self._row(connection, scope, row["task_id"]))

    # 恢复消息按卡片及可选确认请求定位, 并重新关联到原处理任务。
    def bind_continuation(
        self,
        *,
        user_id: int,
        environment: str,
        conversation_id: str,
        task_id: str,
        card_id: str,
        input_message_id: int,
        assistant_message_id: int,
        confirmation_request_id: str | None = None,
    ) -> ProcessingContext:
        scope = self._scope(user_id, environment, conversation_id)
        # 与消息仓库使用同一引用算法, 写确认重发不会生成新关系。
        reference = continuation_reference(card_id, confirmation_request_id)
        with self._factory() as connection:
            task = self._row(connection, scope, task_id, lock=True)
            card = connection.execute(
                "SELECT task_id FROM processing_cards WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND card_id=%s",
                (*scope, card_id),
            ).fetchone()
            # 只有当前任务已绑定的卡片能恢复, 不能提交其他任务的卡片推进本任务。
            if card is None or card["task_id"] != task_id:
                raise BsideError("PROCESSING_CARD_NOT_FOUND", 404)
            # 分别验证恢复消息角色、会话及引用, 再补入任务关系。
            for message_id, role in (
                (input_message_id, "user"),
                (assistant_message_id, "assistant"),
            ):
                row = connection.execute(
                    "UPDATE messages SET content=content || %s::jsonb WHERE id=%s "
                    "AND conversation_id=%s AND role=%s AND ref_kind='temporary_interaction' AND ref_id=%s RETURNING id",
                    (_json({"processingTaskId": task_id}), message_id, scope[2], role, reference),
                ).fetchone()
                if row is None:
                    raise BsideError("PROCESSING_MESSAGE_NOT_FOUND", 404)
            connection.execute(
                "INSERT INTO processing_turns(user_id,environment,conversation_id,request_id,"
                "request_digest,task_id,input_message_id,assistant_message_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                (
                    *scope,
                    "card:" + reference,
                    reference,
                    task_id,
                    input_message_id,
                    assistant_message_id,
                ),
            )
            # 所有待交互卡片关闭后才离开补参状态, 并根据已有真实回执恢复状态。
            if task["status"] == "WAITING_INPUT" and not self._waiting_card(
                connection, scope, task_id
            ):
                # 已取得业务结果的任务恢复为待确认结果, 否则恢复为开放处理中。
                has_result = connection.execute(
                    "SELECT 1 FROM processing_operations WHERE task_id=%s AND status='RETURNED' LIMIT 1",
                    (task_id,),
                ).fetchone()
                connection.execute(
                    "UPDATE processing_tasks SET status=%s,updated_at=now() WHERE task_id=%s",
                    ("RESULT_RECORDED" if has_result else "OPEN", task_id),
                )
            return _context(self._row(connection, scope, task_id))

    # 写入准入必须对应已领取的真实审批请求, 不能从自然语言推断确认。
    @staticmethod
    def _confirmed_write(
        connection: DatabaseConnection,
        scope: tuple[int, str, int],
        task_id: str,
        card_id: str,
        turn_id: str,
        tool_call_id: str,
        ability_key: str,
        encoded: str,
    ) -> bool:
        """Admit only the exact durably claimed card; never infer approval from prose."""
        # 审批卡片 ID 有界且非空, 非法身份直接判定未确认。
        if not isinstance(card_id, str) or not card_id or len(card_id) > 128:
            return False
        row = connection.execute(
            "SELECT c.binding_metadata,r.payload FROM processing_cards p "
            "JOIN chat_a2ui_cards c ON c.user_id=p.user_id AND c.environment=p.environment "
            "AND c.conversation_id=p.conversation_id::text AND c.card_id=p.card_id "
            "JOIN chat_a2ui_action_requests r ON r.user_id=c.user_id AND r.environment=c.environment "
            "AND r.conversation_id=c.conversation_id AND r.card_id=c.card_id "
            "AND r.request_id=c.active_request_id "
            "WHERE p.user_id=%s AND p.environment=%s AND p.conversation_id=%s AND p.task_id=%s "
            "AND p.card_id=%s AND c.status='EXECUTING' AND r.state='CLAIMED'",
            (*scope, task_id, card_id),
        ).fetchone()
        if row is None:
            return False
        # 同时核对卡片任务、轮次、工具调用和原始审批回执。
        metadata = row["binding_metadata"]
        binding = metadata.get("approval", {})
        receipt = binding.get("receipt", {})
        context = metadata.get("approvalProcessingContext", {})
        # 审批身份、参数摘要及明确同意负载必须完全一致, 不能挪用其他确认。
        if (
            metadata.get("definitionSource") != "TEMPORARY"
            or metadata.get("processingTaskId") != task_id
            or context.get("taskId") != task_id
            or context.get("conversationId") != str(scope[2])
            or metadata.get("approvalProcessingTurnId") != turn_id
            or metadata.get("toolCallId") != tool_call_id
            or receipt.get("user_id") != scope[0]
            or receipt.get("environment") != scope[1]
            or receipt.get("run_id") != str(scope[2])
            or receipt.get("tool_call_id") != tool_call_id
            or receipt.get("action_code") != ability_key
            # 仅写入或破坏性操作的显式审批票据可放行, 且提交参数不能被改写。
            or receipt.get("side_effect_level") not in {"WRITE", "DESTRUCTIVE"}
            or receipt.get("approval_policy") != "REQUEST_APPROVAL"
            # 规范化参数与摘要双重核对, 防止确认之后替换业务入参。
            or _json(binding.get("arguments")) != encoded
            or receipt.get("arguments_digest") != hashlib.sha256(encoded.encode()).hexdigest()
            or row["payload"] != {"actionName": "submit", "inputs": {"confirmation": ["approve"]}}
        ):
            return False
        # 同任务不能还有其他未结束卡片, 避免边补参边并发执行下一次操作。
        return (
            connection.execute(
                "SELECT 1 FROM processing_cards p JOIN chat_a2ui_cards c ON c.user_id=p.user_id "
                "AND c.environment=p.environment AND c.conversation_id=p.conversation_id::text "
                "AND c.card_id=p.card_id WHERE p.user_id=%s AND p.environment=%s "
                "AND p.conversation_id=%s AND p.task_id=%s AND p.card_id<>%s "
                "AND c.status IN ('WAITING_ACTION','EXECUTING') LIMIT 1",
                (*scope, task_id, card_id),
            ).fetchone()
            is None
        )

    # 操作先持久化领取, 再调用一次业务服务; 未知回执不自动重试。
    def execute_operation(
        self,
        *,
        user_id: int,
        environment: str,
        conversation_id: str,
        task_id: str,
        turn_id: str,
        tool_call_id: str,
        ability_key: str,
        arguments: Mapping[str, Any],
        invoke: Callable[[str], Mapping[str, Any]],
        confirmation_card_id: str | None = None,
    ) -> OperationEnvelope:
        scope = self._scope(user_id, environment, conversation_id)
        # 校验规范化参数大小, 并将能力与参数一起计算操作去重摘要。
        encoded = _json(dict(arguments))
        if len(encoded.encode()) > 262144 or not ability_key or len(ability_key) > 256:
            raise BsideError("PROCESSING_ARGUMENTS_INVALID", 400)
        digest = hashlib.sha256((ability_key + "\0" + encoded).encode()).hexdigest()
        with self._factory() as connection:
            task = self._row(connection, scope, task_id, lock=True)
            # 工具必须来自已登记的本任务轮次, 不接受任意模型提供的轮次号。
            turn = connection.execute(
                "SELECT 1 FROM processing_turns WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND task_id=%s AND input_message_id::text=%s",
                (*scope, task_id, turn_id),
            ).fetchone()
            # 没有轮次关系即拒绝; 已有相同操作仅返回保存的信封。
            if turn is None:
                raise BsideError("PROCESSING_TURN_NOT_FOUND", 404)
            prior = connection.execute(
                "SELECT * FROM processing_operations WHERE task_id=%s AND operation_digest=%s",
                (task_id, digest),
            ).fetchone()
            # 重复调用只读取已有结果, 包括 RUNNING 或 UNKNOWN, 也不重新派发业务。
            if prior:
                return self._envelope(prior, replayed=True)
            # 若携带写确认卡片, 必须通过完整审批证据验证, 不能略过失败结果。
            confirmed = False
            if confirmation_card_id is not None:
                confirmed = self._confirmed_write(
                    connection,
                    scope,
                    task_id,
                    confirmation_card_id,
                    turn_id,
                    tool_call_id,
                    ability_key,
                    encoded,
                )
                if not confirmed:
                    raise BsideError("PROCESSING_CONFIRMATION_INVALID", 409)
            # 终态和未知任务关闭执行; 等待输入只有本次有效审批可以放行。
            if task["status"] in {"RESOLVED", "FAILED", "UNKNOWN"} or (
                task["status"] == "WAITING_INPUT" and not confirmed
            ):
                raise BsideError("PROCESSING_TASK_NOT_EXECUTABLE", 409)
            # 同任务已有运行中操作时拒绝并发, 避免业务结果和任务状态相互覆盖。
            if connection.execute(
                "SELECT 1 FROM processing_operations WHERE task_id=%s AND status='RUNNING'",
                (task_id,),
            ).fetchone():
                raise BsideError("PROCESSING_OPERATION_IN_PROGRESS", 409)
            # 先生成稳定业务请求号并保存 RUNNING 领取记录, 再离开事务执行。
            operation_id = uuid.uuid4().hex
            request_id = "processing:" + operation_id
            connection.execute(
                "INSERT INTO processing_operations(operation_id,task_id,operation_digest,ability_key,"
                "arguments,turn_id,tool_call_id,request_id,status) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,'RUNNING')",
                (
                    operation_id,
                    task_id,
                    digest,
                    ability_key,
                    encoded,
                    turn_id,
                    tool_call_id,
                    request_id,
                ),
            )
        # Claim committed before invoking: a process crash cannot create a second dispatch.
        # 领取已提交后, 默认结果未知; 只有可验证的业务回执才能改变判断。
        result = None
        error_code = None
        status = "UNKNOWN"
        try:
            # 调用方把保存的请求号传给业务服务, 平台自身不进行二次派发。
            candidate = invoke(request_id)
            if (
                # 校验回执成功字段、请求号、能力和环境, 响应不匹配不能认作本次结果。
                not isinstance(candidate, dict)
                or type(candidate.get("success")) is not bool
                or candidate.get("requestId") != request_id
                or candidate.get("actionCode") != ability_key
                or candidate.get("resolvedEnvironment") != environment
            ):
                error_code = "PROCESSING_RESULT_UNCONFIRMED"
            # 回执也有大小上限, 过大结果不能直接塞进处理历史。
            elif len(_json(candidate).encode()) > 1048576:
                error_code = "PROCESSING_RESULT_TOO_LARGE"
            else:
                result = candidate
                raw_code = candidate.get("errorCode")
                # These execution errors are raised before business dispatch. Transport
                # or response decoding failures cannot establish absence of a side effect.
                # 只有明确发生在派发前的拒绝码能证明未执行; 通信异常不能证明无副作用。
                rejected_before_dispatch = {
                    "TRUSTED_CONTEXT_REQUIRED",
                    "CAPABILITY_CLIENT_NOT_SUPPORTED",
                    "RELEASE_ENVIRONMENT_INVALID",
                    "EXECUTION_PLAN_INVALID",
                    "ARGUMENT_INVALID",
                    "ARGUMENT_TYPE_MISMATCH",
                    "REQUEST_MAPPING_INVALID",
                }
                # 成功保存 RETURNED, 派发前明确拒绝记 FAILED, 其余失败保留 UNKNOWN。
                status = (
                    "RETURNED"
                    if candidate["success"]
                    else ("FAILED" if raw_code in rejected_before_dispatch else "UNKNOWN")
                )
                # 仅保存格式合法的稳定错误码, 不回显任意异常文本。
                if isinstance(raw_code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", raw_code):
                    error_code = raw_code
        # 调用抛错同样保留未知, 禁止凭异常推断业务一定没有执行。
        except Exception:
            error_code = "PROCESSING_DISPATCH_UNCONFIRMED"
        with self._factory() as connection:
            # 回执保存前重新锁任务, 使操作结果和任务摘要同事务更新。
            self._row(connection, scope, task_id, lock=True)
            row = connection.execute(
                "UPDATE processing_operations SET status=%s,result=%s::jsonb,error_code=%s,"
                "finished_at=now() WHERE operation_id=%s RETURNING *",
                (status, _json(result) if result is not None else None, error_code, operation_id),
            ).fetchone()
            # 业务返回、明确失败和未知分别映射任务状态, 不混成已处理。
            task_status = {"RETURNED": "RESULT_RECORDED", "FAILED": "FAILED", "UNKNOWN": "UNKNOWN"}[
                status
            ]
            # 仍有未结束卡片时继续显示等待输入, 真实回执仍独立保留。
            if status == "RETURNED" and self._waiting_card(connection, scope, task_id):
                task_status = "WAITING_INPUT"
            # 展示摘要只描述回执事实, 成功返回后也仍待用户确认解决。
            summary = ability_key + (
                "：已返回执行结果，待确认"
                if status == "RETURNED"
                else "：执行失败"
                if status == "FAILED"
                else "：执行结果未知"
            )
            connection.execute(
                "UPDATE processing_tasks SET status=%s,result_summary=%s,updated_at=now() WHERE task_id=%s",
                (task_status, summary, task_id),
            )
            assert row is not None
            return self._envelope(row, replayed=False)

    # 相同信封用于首次返回和幂等读取, replayed 明确标记读取已有事实。
    @staticmethod
    def _envelope(row: Mapping[str, Any], *, replayed: bool) -> OperationEnvelope:
        return {
            "status": row["status"],
            "operationId": row["operation_id"],
            "requestId": row["request_id"],
            "replayed": replayed,
            "result": row["result"],
            "errorCode": row["error_code"],
        }

    # 处理任务展示状态取最近已绑定的助手消息, 不能从业务操作状态推断模型已结束。
    @staticmethod
    def _delivery(connection: DatabaseConnection, task_id: str) -> str | None:
        row = connection.execute(
            "SELECT m.content->>'delivery' delivery FROM processing_turns t "
            "JOIN messages m ON m.id=t.assistant_message_id AND m.conversation_id=t.conversation_id "
            "WHERE t.task_id=%s ORDER BY t.input_message_id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        return row["delivery"] if row else None

    # 任务详情按用户和环境隔离, 附加最多一百条真实操作历史。
    def get(self, *, user_id: int, environment: str, task_id: str) -> dict[str, Any]:
        require_user_id(user_id)
        with self._factory() as connection:
            row = connection.execute(
                "SELECT * FROM processing_tasks WHERE user_id=%s AND environment=%s AND task_id=%s",
                (user_id, environment, task_id),
            ).fetchone()
            if row is None:
                raise BsideError("PROCESSING_TASK_NOT_FOUND", 404)
            # 分别查询模型交付状态与业务操作记录, 保留两种状态的差异。
            delivery = self._delivery(connection, task_id)
            operations = connection.execute(
                "SELECT * FROM processing_operations WHERE task_id=%s ORDER BY created_at,operation_id LIMIT 100",
                (task_id,),
            ).fetchall()
        return {
            **_context(row),
            "deliveryStatus": delivery,
            "createdAt": _time(row["created_at"]),
            "updatedAt": _time(row["updated_at"]),
            "resultSummary": row["result_summary"],
            "resolutionSummary": row["resolution_summary"],
            "resolvedAt": _time(row["resolved_at"]),
            # 只有用户显式确认保存了解决时间, 才标记确认来源。
            "resolutionSource": "USER_CONFIRMATION" if row["resolved_at"] else None,
            # 公开操作 ID、工具调用号和真实回执, 便于追溯结果来自哪次执行。
            "operations": [
                {
                    "operationId": o["operation_id"],
                    "abilityKey": o["ability_key"],
                    "status": o["status"],
                    "requestId": o["request_id"],
                    "turnId": o["turn_id"],
                    "toolCallId": o["tool_call_id"],
                    "createdAt": _time(o["created_at"]),
                    "finishedAt": _time(o["finished_at"]),
                    "result": o["result"],
                    "errorCode": o["error_code"],
                }
                for o in operations
            ],
        }

    # 解决任务是显式用户确认, 不会因阅读通知或模型给出总结而自动关闭。
    def resolve(
        self, *, user_id: int, environment: str, task_id: str, summary: str
    ) -> dict[str, Any]:
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 2000:
            raise BsideError("PROCESSING_RESOLUTION_REQUIRED", 400)
        with self._factory() as connection:
            row = connection.execute(
                "SELECT * FROM processing_tasks WHERE user_id=%s AND environment=%s AND task_id=%s FOR UPDATE",
                (user_id, environment, task_id),
            ).fetchone()
            if row is None:
                raise BsideError("PROCESSING_TASK_NOT_FOUND", 404)
            # 已解决任务的重复确认必须摘要相同, 否则报告幂等冲突。
            if row["status"] == "RESOLVED":
                if row["resolution_summary"] != summary.strip():
                    raise BsideError("PROCESSING_RESOLUTION_CONFLICT", 409)
            # 只有真实结果已记录、模型已交付、无待交互及无异常操作, 才允许解决。
            elif (
                row["status"] != "RESULT_RECORDED"
                or self._delivery(connection, task_id) not in {"completed", "waiting_action"}
                or self._waiting_card(
                    connection, (user_id, environment, row["conversation_id"]), task_id
                )
                or connection.execute(
                    "SELECT 1 FROM processing_operations WHERE task_id=%s AND status IN ('RUNNING','UNKNOWN','FAILED')",
                    (task_id,),
                ).fetchone()
            ):
                raise BsideError("PROCESSING_RESULT_NOT_CONFIRMED", 409)
            # 满足门禁后保存用户总结与解决时间, 不修改原业务操作回执。
            else:
                connection.execute(
                    "UPDATE processing_tasks SET status='RESOLVED',resolution_summary=%s,resolved_at=now(),"
                    "updated_at=now() WHERE task_id=%s",
                    (summary.strip(), task_id),
                )
        return self.get(user_id=user_id, environment=environment, task_id=task_id)
