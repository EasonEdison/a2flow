"""Product turn inbox and dispatch. Never infer permission to replay from a lease."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_workflow_runtime.chat.cards import CardCompletion
from skillweave_contracts.chat_state import FINAL_DELIVERIES, ProductTurnStatus, TurnSource

from .chat_delivery import ChatDelivery, restore_content
from .chat_runner import ChatRunner
from .chat_wake import ChatWake
from .errors import BsideError
from .interaction_continuation import continuation_reference
from .persistence_types import ConnectionFactory, DatabaseConnection, MessageRecord, message_record
from .processing_tasks import ProcessingContext, ProcessingTasksRepository
from .repositories import MessagesRepository
from .turn_registry import TurnRegistry
from .turn_registry import digest as payload_digest

_LOG = logging.getLogger(__name__)


# 使用排序键和固定分隔符序列化, 幂等摘要不受对象键顺序影响。
def encoded(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


# 产品层保存接收事实、恢复意图和展示事件, 不维护另一套 Agent 执行图。
class DurableChat:
    def __init__(
        self, factory: ConnectionFactory, *, environment: str, wake: ChatWake | None = None
    ) -> None:
        self.factory, self.environment = factory, environment
        self.wake = wake if wake is not None else ChatWake()

    # 启动前检查持久化接收与续聊表可用, 避免接受无法恢复的请求。
    def check_ready(self) -> None:
        with self.factory() as c:
            c.execute(
                "SELECT input_message_id,source_kind,source_key,source_digest,processing_task_id "
                "FROM chat_turns LIMIT 0"
            )
            invalid = c.execute(
                "SELECT 1 FROM chat_turns WHERE source_kind IS NULL OR source_key IS NULL "
                "OR source_digest IS NULL OR source_kind NOT IN "
                "('USER_MESSAGE','PROCESSING','CARD_CONTINUATION') OR "
                "status NOT IN ('QUEUED','RUNNING','COMPLETED','NEEDS_REVIEW') LIMIT 1"
            ).fetchone()
            if invalid:
                raise RuntimeError("CHAT_STATE_SCHEMA_INCOMPATIBLE")
            c.execute("SELECT reference,state FROM chat_continuations LIMIT 0")
            c.execute(
                "SELECT user_id,environment,conversation_id,client_request_id,request_digest,"
                "input_message_id FROM chat_requests LIMIT 0"
            )
            c.execute(
                "SELECT input_message_id,sequence,dispatch_generation,event FROM chat_turn_events LIMIT 0"
            )
            legacy = c.execute(
                "SELECT to_regclass('processing_turns') IS NOT NULL OR EXISTS("
                "SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() "
                "AND ((table_name='chat_turns' AND column_name IN ('request_id','request_digest')) "
                "OR (table_name='chat_requests' AND column_name='assistant_message_id') "
                "OR (table_name='chat_continuations' AND column_name IN ('materialized','recovery_status')))) "
                "AS incompatible"
            ).fetchone()
            assert legacy is not None
            if legacy["incompatible"]:
                raise RuntimeError("CHAT_STATE_SCHEMA_INCOMPATIBLE")

    # 请求号按用户、环境和会话隔离, 并将负载摘要与已保存请求比对。
    def request(
        self, *, user_id: int, conversation_id: int, request_id: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        digest = payload_digest(payload)
        with self.factory() as c:
            row = c.execute(
                "SELECT r.*,t.assistant_message_id,t.status FROM chat_requests r "
                "JOIN chat_turns t USING(input_message_id) WHERE r.user_id=%s AND r.environment=%s "
                "AND r.conversation_id=%s AND r.client_request_id=%s",
                (user_id, self.environment, conversation_id, request_id),
            ).fetchone()
            # 相同请求号搭配不同内容必须报冲突, 不能悄悄复用或覆盖原执行。
            if row and row["request_digest"] != digest:
                raise BsideError("CHAT_REQUEST_CONFLICT", 409)
            return dict(row) if row else None

    # 轮次与消息使用同一事务保存, 引用及处理上下文冻结为接收时的事实。
    def insert_turn(
        self,
        c: DatabaseConnection,
        *,
        user_id: int,
        conversation_id: int,
        source_kind: TurnSource,
        source_key: str,
        source_digest: str,
        input_message: MessageRecord,
        assistant_message: MessageRecord,
        references: Sequence[dict[str, Any]] = (),
        processing_context: ProcessingContext | None = None,
    ) -> None:
        TurnRegistry.insert(
            c,
            user_id=user_id,
            environment=self.environment,
            conversation_id=conversation_id,
            source_kind=source_kind,
            source_key=source_key,
            source_digest=source_digest,
            input_message=input_message,
            assistant_message=assistant_message,
            references=references,
            processing_context=processing_context,
        )

    # 普通消息以会话行锁串行准入, 原消息、助手占位和待分发轮次一起提交。
    def receive(
        self,
        *,
        user_id: int,
        conversation_id: int,
        request_id: str,
        payload: dict[str, Any],
        references: list[dict[str, Any]],
    ) -> dict[str, Any]:
        digest = payload_digest(payload)
        with self.factory() as c:
            # 事务内再次检查归属, 不能只依赖路由先前的读取。
            owner = c.execute(
                "SELECT user_id FROM conversations WHERE id=%s FOR UPDATE",
                (conversation_id,),
            ).fetchone()
            if owner is None or owner["user_id"] != user_id:
                raise BsideError("CONVERSATION_NOT_FOUND", 404)
            # 先找同请求轮次; 已存在时核对摘要并返回, 不插入第二对消息。
            prior = c.execute(
                "SELECT * FROM chat_turns WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND source_kind='USER_MESSAGE' AND source_key=%s",
                (user_id, self.environment, conversation_id, request_id),
            ).fetchone()
            if prior:
                if prior["source_digest"] != digest:
                    raise BsideError("CHAT_REQUEST_CONFLICT", 409)
                return dict(prior)
            # 用户消息保存真实输入与引用, 助手消息以 queued 占位等待后台执行。
            rows: list[MessageRecord] = []
            for role, content in [
                (
                    "user",
                    {
                        "text": payload["text"],
                        "delivery": "submitted",
                        "clientRequestId": request_id,
                        "runReferences": references,
                    },
                ),
                ("assistant", {"text": "", "delivery": "queued", "parts": []}),
            ]:
                rows.append(
                    message_record(
                        c.execute(
                            "INSERT INTO messages(conversation_id,role,content) "
                            "VALUES (%s,%s,%s::jsonb) RETURNING *",
                            (conversation_id, role, encoded(content)),
                        ).fetchone()
                    )
                )
            # 消息成功插入后建立待执行轮次, 外部订阅不直接调模型。
            self.insert_turn(
                c,
                user_id=user_id,
                conversation_id=conversation_id,
                source_kind=TurnSource.USER_MESSAGE,
                source_key=request_id,
                source_digest=digest,
                input_message=rows[0],
                assistant_message=rows[1],
                references=references,
            )
            # 同时登记客户端幂等映射, 确保网络重发能查回同一次准入。
            TurnRegistry.map_request(
                c,
                environment=self.environment,
                user_id=user_id,
                conversation_id=conversation_id,
                request_id=request_id,
                payload=payload,
                input_message=rows[0],
            )
            row = c.execute(
                "SELECT * FROM chat_turns WHERE input_message_id=%s", (rows[0]["id"],)
            ).fetchone()
            assert row is not None
            return dict(row)

    # 卡片完成观察沿用动作事务, 将自动续聊意图与真实提交一起保存。
    def observe_completion(
        self, connection: DatabaseConnection, completion: CardCompletion
    ) -> None:
        metadata = completion.metadata
        # Workflow completions are owned by the Workflow outbox, never Chat.
        # 工作流卡片由 Workflow outbox 恢复, 不能再进入 Chat 重复推进。
        if metadata.get("workflow"):
            return
        # 仅处理临时交互与写审批, 普通卡片完成不自动生成新对话。
        write = "approval" in metadata or "completedApproval" in metadata
        if not write and metadata.get("definitionSource") != "TEMPORARY":
            return
        # 写审批按具体确认请求去重, 普通临时表单按卡片去重。
        reference = continuation_reference(
            completion.card_id, completion.request_id if write else None
        )
        connection.execute(
            "INSERT INTO chat_continuations(user_id,environment,conversation_id,reference,"
            "card_id,request_id,write_completed) VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (
                completion.owner.user_id,
                self.environment,
                int(completion.conversation_id),
                reference,
                completion.card_id,
                completion.request_id,
                write,
            ),
        )

    # 按输入消息 ID 查询保存轮次, 供拿锁后的状态复核。
    def get(self, input_id: int) -> dict[str, Any] | None:
        with self.factory() as c:
            row = c.execute(
                "SELECT * FROM chat_turns WHERE input_message_id=%s", (input_id,)
            ).fetchone()
            return dict(row) if row else None

    # 同事务创建的消息对按 ID 排序读取, 不重建用户输入内容。
    def pair(self, turn: dict[str, Any]) -> tuple[MessageRecord, MessageRecord]:
        with self.factory() as c:
            rows = c.execute(
                "SELECT * FROM messages WHERE id IN (%s,%s) ORDER BY id",
                (turn["input_message_id"], turn["assistant_message_id"]),
            ).fetchall()
            return message_record(rows[0]), message_record(rows[1])

    # 有待核对前序轮次时阻止后续消息执行, 避免在未知业务事实之上继续推理。
    def candidates(
        self,
        *,
        exclude_conversations: Sequence[int] = (),
        limit: int = 32,
        after_input_id: int = 0,
    ) -> list[dict[str, Any]]:
        if type(limit) is not int or limit < 1:
            raise ValueError("CHAT_CANDIDATE_LIMIT_INVALID")
        with self.factory() as c:
            blocked = c.execute(
                "UPDATE chat_turns t SET status='NEEDS_REVIEW',updated_at=now() "
                "WHERE t.environment=%s AND t.status='QUEUED' AND EXISTS(SELECT 1 FROM chat_turns p "
                "WHERE p.environment=t.environment AND p.conversation_id=t.conversation_id "
                "AND p.input_message_id<t.input_message_id AND p.status='NEEDS_REVIEW') "
                "RETURNING t.assistant_message_id",
                (self.environment,),
            ).fetchall()
            # 被前序阻塞的助手投影明确写入原因, 页面不能一直显示正常排队。
            for row in blocked:
                c.execute(
                    "UPDATE messages SET content=content || %s::jsonb WHERE id=%s",
                    (
                        encoded(
                            {
                                "delivery": "unconfirmed",
                                "errorCode": "CHAT_PREVIOUS_TURN_REQUIRES_REVIEW",
                            }
                        ),
                        row["assistant_message_id"],
                    ),
                )
            # 每个会话只选没有未结束前序的候选, 跨会话仍可并发。
            return [
                dict(row)
                for row in c.execute(
                    "SELECT t.* FROM chat_turns t WHERE t.environment=%s "
                    "AND t.status IN ('QUEUED','RUNNING') AND t.next_attempt_at<=now() "
                    "AND NOT (t.conversation_id=ANY(%s::bigint[])) "
                    "AND NOT EXISTS(SELECT 1 FROM chat_turns p WHERE p.conversation_id=t.conversation_id "
                    "AND p.environment=t.environment AND p.input_message_id<t.input_message_id "
                    "AND p.status IN ('QUEUED','RUNNING','NEEDS_REVIEW')) "
                    "ORDER BY (t.input_message_id<=%s),t.input_message_id LIMIT %s",
                    (self.environment, list(exclude_conversations), after_input_id, limit),
                ).fetchall()
            ]

    def next_delay(
        self, *, exclude_conversations: Sequence[int] = (), include_turns: bool = True
    ) -> float | None:
        """Next eligible database deadline; a wake hint never changes retry permission."""
        with self.factory() as c:
            # 与候选使用同一前序阻断条件, 未来轮次不能越过未确认或运行中的前序。
            row = c.execute(
                "SELECT CASE WHEN min(next_attempt_at) IS NULL THEN NULL ELSE "
                "GREATEST(0,EXTRACT(EPOCH FROM min(next_attempt_at)-now())) END AS seconds "
                "FROM (SELECT t.next_attempt_at FROM chat_turns t WHERE t.environment=%s "
                "AND %s AND t.status IN ('QUEUED','RUNNING') "
                "AND NOT (t.conversation_id=ANY(%s::bigint[])) "
                "AND NOT EXISTS(SELECT 1 FROM chat_turns p WHERE p.conversation_id=t.conversation_id "
                "AND p.environment=t.environment AND p.input_message_id<t.input_message_id "
                "AND p.status IN ('QUEUED','RUNNING','NEEDS_REVIEW')) "
                "UNION ALL SELECT next_attempt_at FROM chat_continuations "
                "WHERE environment=%s AND state='PENDING') deadlines",
                (self.environment, include_turns, list(exclude_conversations), self.environment),
            ).fetchone()
            assert row is not None
            return None if row["seconds"] is None else float(row["seconds"])

    def defer(self, input_id: int, generation: int, seconds: float = 2.0) -> None:
        """Bounded scheduling retry only; never alter execution or terminal facts."""
        if seconds < 0 or not seconds < float("inf"):
            raise ValueError("CHAT_RETRY_DELAY_INVALID")
        with self.factory() as c:
            c.execute(
                "UPDATE chat_turns SET next_attempt_at=GREATEST(next_attempt_at,now()+%s*interval '1 second'),"
                "updated_at=now() "
                "WHERE input_message_id=%s AND dispatch_generation=%s "
                "AND status IN ('QUEUED','RUNNING')",
                (seconds, input_id, generation),
            )

    # 会话级 PostgreSQL 锁跨事务持有, 只用于产品分发协调。
    @contextmanager
    def lock(self, conversation_id: int) -> Iterator[bool]:
        with self.factory() as c:
            # 独立连接持有会话锁, 事务提交不会提前释放分发权。
            c.autocommit = True
            key = "bside-chat:" + self.environment + ":" + str(conversation_id)
            acquired_row = c.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired",
                (key,),
            ).fetchone()
            assert acquired_row is not None
            acquired = acquired_row["acquired"]
            # 无论执行路径如何退出都释放已取得的锁, 未取得时不误解锁。
            try:
                yield acquired
            finally:
                if acquired:
                    c.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))

    # 每次接管增加代际, 旧生产者即使仍存活也不能覆盖新投影。
    def claim_generation(self, input_id: int) -> int | None:
        with self.factory() as c:
            row = c.execute(
                "UPDATE chat_turns SET dispatch_generation=dispatch_generation+1 "
                "WHERE input_message_id=%s AND status IN ('QUEUED','RUNNING') "
                "AND next_attempt_at<=now() RETURNING dispatch_generation",
                (input_id,),
            ).fetchone()
            return row["dispatch_generation"] if row else None

    # 状态更新受代际与当前状态双重约束, 过期写入者无权推进终态。
    def set_status(self, input_id: int, status: ProductTurnStatus, generation: int) -> None:
        with self.factory() as c:
            c.execute(
                "UPDATE chat_turns SET status=%s,next_attempt_at=now()+interval '2 seconds',updated_at=now() "
                "WHERE input_message_id=%s AND dispatch_generation=%s AND status IN ('QUEUED','RUNNING')",
                (status, input_id, generation),
            )

    # 写消息前锁定对应轮次并核对代际、会话和助手消息身份。
    def save_projection(
        self,
        input_id: int,
        generation: int,
        *,
        conversation_id: int,
        message_id: int,
        content: dict[str, Any],
    ) -> None:
        with self.factory() as c:
            row = c.execute(
                "SELECT assistant_message_id,conversation_id FROM chat_turns WHERE input_message_id=%s "
                "AND dispatch_generation=%s AND status IN ('QUEUED','RUNNING') FOR UPDATE",
                (input_id, generation),
            ).fetchone()
            # 任一绑定不一致都视为写入者失效, 禁止覆盖别的消息。
            if (
                row is None
                or row["assistant_message_id"] != message_id
                or row["conversation_id"] != conversation_id
            ):
                raise RuntimeError("CHAT_DISPATCH_FENCED")
            c.execute(
                "UPDATE messages SET content=%s::jsonb WHERE id=%s",
                (encoded(content), message_id),
            )
            # 展示终态和产品调度完成共用本事务，崩溃不会留下已交付但仍可派发的轮次。
            if content.get("delivery") in FINAL_DELIVERIES:
                c.execute(
                    "UPDATE chat_turns SET status='COMPLETED',updated_at=now() "
                    "WHERE input_message_id=%s AND dispatch_generation=%s",
                    (input_id, generation),
                )

    # 事件日志写入与代际检查共用行锁, 防止丢锁的旧实例继续发布。
    def event(self, input_id: int, event: dict[str, Any], generation: int) -> None:
        with self.factory() as c:
            # Lock the generation row through journal commit, fencing a writer
            # whose advisory-lock connection disappeared while its producer lived.
            row = c.execute(
                "SELECT 1 FROM chat_turns WHERE input_message_id=%s AND dispatch_generation=%s "
                "AND status='RUNNING' FOR UPDATE",
                (input_id, generation),
            ).fetchone()
            # 不再拥有当前 RUNNING 代际时直接拒绝, 不把旧结果混入新事件流。
            if row is None:
                raise RuntimeError("CHAT_DISPATCH_FENCED")
            c.execute(
                "INSERT INTO chat_turn_events(input_message_id,sequence,event,dispatch_generation) "
                "VALUES (%s,%s,%s::jsonb,%s) "
                "ON CONFLICT(input_message_id,sequence) DO UPDATE SET event=excluded.event "
                "WHERE chat_turn_events.dispatch_generation=excluded.dispatch_generation",
                (input_id, event["sequence"], encoded(event), generation),
            )

    def event_cursor(self, input_id: int) -> int:
        """New generations append after the saved transport cursor, never restart at one."""
        with self.factory() as c:
            row = c.execute(
                "SELECT COALESCE(max(sequence),1) AS sequence FROM chat_turn_events WHERE input_message_id=%s",
                (input_id,),
            ).fetchone()
            assert row is not None
            return int(row["sequence"])

    # 订阅者只读事件日志和投影; 断开、刷新或重连都不会执行模型。
    async def stream(self, turn: dict[str, Any]) -> AsyncIterator[str]:
        input_id = turn["input_message_id"]
        # 轮次开始作为订阅引导事件, 后续从保存日志的下一序号读取。
        cursor = 1
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "turn_started",
                    "sequence": 1,
                    "turnId": str(input_id),
                    "inputMessageId": str(input_id),
                    "messageId": str(turn["assistant_message_id"]),
                }
            )
            + "\n\n"
        )
        # 批量读取游标之后的日志并查询当前轮次状态, 全部在线程中进行。
        while True:

            def read() -> tuple[list[dict[str, Any]], str]:
                with self.factory() as c:
                    events = c.execute(
                        "SELECT sequence,event FROM chat_turn_events WHERE input_message_id=%s "
                        "AND sequence>%s ORDER BY sequence",
                        (input_id, cursor),
                    ).fetchall()
                    current = c.execute(
                        "SELECT status FROM chat_turns WHERE input_message_id=%s",
                        (input_id,),
                    ).fetchone()
                    assert current is not None
                    return events, current["status"]

            # 按日志序号发出保存事件, 终态事件存在时直接结束订阅。
            events, status = await asyncio.to_thread(read)
            for row in events:
                cursor = row["sequence"]
                yield "data: " + json.dumps(row["event"], ensure_ascii=False) + "\n\n"
                if row["event"].get("type") in {"done", "error"}:
                    return
            # 终态已保存但终态事件缺失时, 用真实消息投影修复响应。
            if status in {"COMPLETED", "NEEDS_REVIEW"}:
                # A crash can occur between final projection and event; return a factual snapshot.
                _, assistant = await asyncio.to_thread(self.pair, turn)
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "done" if status == "COMPLETED" else "error",
                            "sequence": cursor + 1,
                            "turnId": str(input_id),
                            "inputMessageId": str(input_id),
                            "messageId": str(turn["assistant_message_id"]),
                            "content": assistant["content"],
                            "code": None if status == "COMPLETED" else "CHAT_REQUIRES_REVIEW",
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                return
            # 仍在排队或执行时发送心跳, 只等待事实, 不触发执行重试。
            yield ": pending\n\n"
            await asyncio.sleep(0.4)

    # 扫描尚未物化的续聊意图, 每批有上限, 单条失败不阻塞其他会话。
    def materialize(
        self, messages: MessagesRepository, processing_tasks: ProcessingTasksRepository | None
    ) -> None:
        with self.factory() as c:
            intents = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM chat_continuations WHERE environment=%s "
                    "AND state='PENDING' AND next_attempt_at<=now() "
                    "ORDER BY created_at LIMIT 32",
                    (self.environment,),
                ).fetchall()
            ]
        # 仅重试本地幂等准备, 物化阶段本身不调用模型或业务工具。
        failure_state_unavailable = False
        for intent in intents:
            try:
                self._materialize_one(intent, messages, processing_tasks)
            except Exception as error:
                # Only local, idempotent preparation is retried. No model or business
                # dispatch happens here. A broken binding cannot starve other chats.
                try:
                    self._materialization_failed(intent, error)
                except Exception:
                    failure_state_unavailable = True
                    _LOG.exception("Chat continuation failure-state persistence failed")
        # 本批其他意图仍先处理; 无法保存失败或重查期限时交由调度层有界退避。
        if failure_state_unavailable:
            raise RuntimeError("CHAT_CONTINUATION_FAILURE_STATE_UNAVAILABLE")

    # 可预期的非服务端错误转人工核对, 暂时故障保留待准备并延迟重试。
    def _materialization_failed(self, intent: dict[str, Any], error: Exception) -> None:
        review = isinstance(error, BsideError) and error.status < 500
        # 恢复状态按完整意图身份更新, 避免不同用户或会话相互影响。
        scope = (
            intent["user_id"],
            self.environment,
            intent["conversation_id"],
            intent["reference"],
        )
        with self.factory() as c:
            changed = c.execute(
                "UPDATE chat_continuations SET state=%s,error_code=%s,"
                "next_attempt_at=now()+interval '5 seconds' WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND reference=%s AND state='PENDING' RETURNING reference",
                (
                    "NEEDS_REVIEW" if review else "PENDING",
                    error.code
                    if isinstance(error, BsideError)
                    else "CHAT_CONTINUATION_PREPARATION_PENDING",
                    *scope,
                ),
            ).fetchone()
            # 只有明确需要核对且状态更新成功时, 才同步修正关联展示。
            if not changed or not isinstance(error, BsideError) or not review:
                return
            rows = c.execute(
                "SELECT * FROM messages WHERE conversation_id=%s AND ref_kind='temporary_interaction' "
                "AND ref_id=%s ORDER BY id",
                (intent["conversation_id"], intent["reference"]),
            ).fetchall()
            # 恢复消息必须恰好是一对, 结构不完整时不能制造新的执行输入。
            pair = {row["role"]: message_record(row) for row in rows}
            if len(rows) == 2 and set(pair) == {"user", "assistant"}:
                # 对已存在的恢复消息幂等登记轮次, 并标为待核对以阻止盲目运行。
                self.insert_turn(
                    c,
                    user_id=intent["user_id"],
                    conversation_id=intent["conversation_id"],
                    source_kind=TurnSource.CARD_CONTINUATION,
                    source_key=intent["reference"],
                    source_digest=intent["reference"],
                    input_message=pair["user"],
                    assistant_message=pair["assistant"],
                )
                c.execute(
                    "UPDATE chat_turns SET status='NEEDS_REVIEW',updated_at=now() WHERE input_message_id=%s",
                    (pair["user"]["id"],),
                )
                c.execute(
                    "UPDATE messages SET content=content || %s::jsonb WHERE id=%s",
                    (
                        encoded({"delivery": "unconfirmed", "errorCode": error.code}),
                        pair["assistant"]["id"],
                    ),
                )

    # 先创建稳定恢复消息, 再绑定处理任务, 最后同事务登记轮次并标记意图完成。
    def _materialize_one(
        self,
        intent: dict[str, Any],
        messages: MessagesRepository,
        processing_tasks: ProcessingTasksRepository | None,
    ) -> None:
        # Each step is idempotent. Intent remains durable until binding and dispatch are saved.
        # 反复物化复用同一卡片确认对应的消息对, 避免崩溃后多发一轮。
        _, user, assistant = messages.claim_interaction_continuation(
            user_id=intent["user_id"],
            conversation_id=intent["conversation_id"],
            card_id=intent["card_id"],
            request_id=intent["request_id"],
            write_completed=intent["write_completed"],
        )
        context = None
        # 仅在卡片确实属于处理任务时恢复任务上下文, 不凭会话猜测归属。
        if processing_tasks is not None:
            context = processing_tasks.context_for_card(
                user_id=intent["user_id"],
                environment=self.environment,
                conversation_id=str(intent["conversation_id"]),
                card_id=intent["card_id"],
            )
            # 写恢复包含确认请求号, 使一次新确认与旧确认重发可以区分。
            if context:
                context = processing_tasks.bind_continuation(
                    user_id=intent["user_id"],
                    environment=self.environment,
                    conversation_id=str(intent["conversation_id"]),
                    task_id=context["taskId"],
                    card_id=intent["card_id"],
                    input_message_id=user["id"],
                    assistant_message_id=assistant["id"],
                    confirmation_request_id=intent["request_id"]
                    if intent["write_completed"]
                    else None,
                )
        # 待执行轮次与物化完成标记一起提交, 避免意图丢失或重复分发。
        with self.factory() as c:
            # 与失败隔离路径统一先锁意图，再登记轮次，避免锁顺序反转和终态回退。
            saved = c.execute(
                "SELECT state FROM chat_continuations WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND reference=%s FOR UPDATE",
                (
                    intent["user_id"],
                    self.environment,
                    intent["conversation_id"],
                    intent["reference"],
                ),
            ).fetchone()
            if saved is None or saved["state"] != "PENDING":
                return
            self.insert_turn(
                c,
                user_id=intent["user_id"],
                conversation_id=intent["conversation_id"],
                source_kind=TurnSource.CARD_CONTINUATION,
                source_key=intent["reference"],
                source_digest=intent["reference"],
                input_message=user,
                assistant_message=assistant,
                processing_context=context,
            )
            c.execute(
                "UPDATE chat_continuations SET state='MATERIALIZED',error_code=NULL WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND reference=%s",
                (
                    intent["user_id"],
                    self.environment,
                    intent["conversation_id"],
                    intent["reference"],
                ),
            )

        # 只有轮次与物化状态的事务成功提交后才发进程内提示。
        self.wake.notify()


# 给消息投影附加输入身份及执行代际, 阻止过期任务写入。
class _FencedProjection:
    def __init__(self, store: DurableChat, input_id: int, generation: int) -> None:
        self.store, self.input_id, self.generation = store, input_id, generation

    def update_delivery(
        self, *, conversation_id: int, message_id: int, content: dict[str, Any]
    ) -> None:
        self.store.save_projection(
            self.input_id,
            self.generation,
            conversation_id=conversation_id,
            message_id=message_id,
            content=content,
        )


# 分发器管理产品收件箱, 原生运行器仍是执行准入和完成事实的权威。
class DurableDispatcher:
    def __init__(
        self,
        store: DurableChat,
        messages: MessagesRepository,
        runner: ChatRunner,
        processing_tasks: ProcessingTasksRepository | None = None,
        *,
        reconcile_seconds: float = 30.0,
        max_concurrency: int = 8,
        retry_seconds: float = 2.0,
    ) -> None:
        if (
            not math.isfinite(reconcile_seconds)
            or reconcile_seconds <= 0
            or not math.isfinite(retry_seconds)
            or retry_seconds <= 0
            or isinstance(max_concurrency, bool)
            or not isinstance(max_concurrency, int)
            or max_concurrency < 1
        ):
            raise ValueError("INVALID_CHAT_DISPATCH_CONFIGURATION")
        self.reconcile_seconds = reconcile_seconds
        self.max_concurrency = max_concurrency
        self.retry_seconds = retry_seconds
        self.store, self.messages, self.runner, self.processing_tasks = (
            store,
            messages,
            runner,
            processing_tasks,
        )
        # 内存集合只减少本进程重复调度, 跨进程安全仍由数据库锁和代际保证。
        self.active: set[int] = set()

    async def dispatch(self, turn: dict[str, Any]) -> bool:
        # Dedicated session lock survives transaction commits; Runtime independently
        # arbitrates actual execution. Lock loss never authorizes business replay.
        # 先取得会话锁再重新读取当前轮次, 候选扫描结果不直接授权执行。
        with self.store.lock(turn["conversation_id"]) as acquired:
            if not acquired:
                # 争锁失败者不修改共享期限，避免在持锁者认领前将其反复延期。
                return False
            # 拿锁后复核轮次仍可处理, 已结束状态不再分配执行代际。
            current = await asyncio.to_thread(self.store.get, turn["input_message_id"])
            assert current is not None
            if current["status"] not in {"QUEUED", "RUNNING"}:
                return True
            # 领取新代际后构建受保护写入器, 旧代际不能覆盖本轮投影。
            generation = await asyncio.to_thread(
                self.store.claim_generation, turn["input_message_id"]
            )
            if generation is None:
                return True
            projection = _FencedProjection(self.store, turn["input_message_id"], generation)
            # 执行前必须问原生运行器：尚未开始、忙碌、已完成还是待核对。
            facts = await self.runner.inspect_turn(
                user_id=turn["user_id"],
                conversation_id=turn["conversation_id"],
                turn_id=str(turn["input_message_id"]),
            )
            state = facts["status"]
            # 原生层仍在执行时延后查询, 绝不因产品锁空闲就重复发起。
            if state == "BUSY":
                await asyncio.to_thread(
                    self.store.set_status,
                    turn["input_message_id"],
                    current["status"],
                    generation,
                )
                return True
            # 使用原来保存的消息对修复或执行, 不接受新文本替换原轮输入。
            user, assistant = await asyncio.to_thread(self.store.pair, turn)
            # 原生结果未知时保存未确认展示并阻止后续自动执行。
            if state == "NEEDS_REVIEW":
                content = {
                    **assistant["content"],
                    "delivery": "unconfirmed",
                    "errorCode": "CHAT_REQUIRES_REVIEW",
                }
                await asyncio.to_thread(
                    projection.update_delivery,
                    conversation_id=turn["conversation_id"],
                    message_id=assistant["id"],
                    content=content,
                )
                await asyncio.to_thread(
                    self.store.set_status,
                    turn["input_message_id"],
                    ProductTurnStatus.NEEDS_REVIEW,
                    generation,
                )
                return True
            # 只有明确未开始才能真实执行, 已完成则只修复完整结果快照。
            if state not in {"NOT_STARTED", "COMPLETED"}:
                raise ValueError("INVALID_RUNTIME_TURN_STATUS")
            await asyncio.to_thread(
                self.store.set_status,
                turn["input_message_id"],
                ProductTurnStatus.RUNNING,
                generation,
            )
            if state == "COMPLETED":
                # 完整原生快照只修复展示和调度终态，不重新归并 token 或调用模型工具。
                content = restore_content(
                    facts["result"],
                    input_message=user,
                    assistant_message=assistant,
                )
                await asyncio.to_thread(
                    projection.update_delivery,
                    conversation_id=turn["conversation_id"],
                    message_id=assistant["id"],
                    content=content,
                )
                return True
            # 只有原生 NOT_STARTED 才构建新执行的投影消费器。
            delivery = ChatDelivery(
                messages=projection,
                runner=self.runner,
                user_id=turn["user_id"],
                conversation_id=turn["conversation_id"],
                text=user["content"]["text"],
                input_message=user,
                assistant_message=assistant,
                run_references=turn["run_references"],
                processing_context=turn["processing_context"],
            )
            # 持久化分发不依赖内存 HTTP 队列, 事件改写入数据库日志。
            delivery.detach()
            journal_sequence = await asyncio.to_thread(self.store.event_cursor, user["id"])

            # 先保存非终态公开事件; 最终状态等原生迭代器退出后再由事实确定。
            async def emit(event: dict[str, Any]) -> None:
                nonlocal journal_sequence
                # 传输日志游标不修改共享结果归并器的原生事件序号。
                journal_sequence += 1
                # Errors remain recoverable through inspect; no premature terminal event.
                if event["type"] in {"error", "done", "turn_started"}:
                    return
                await asyncio.to_thread(
                    self.store.event,
                    user["id"],
                    {
                        **event,
                        "sequence": journal_sequence,
                        "messageId": str(assistant["id"]),
                        "inputMessageId": str(user["id"]),
                    },
                    generation,
                )

            # 显式替换事件接收回调, 消费执行结果并保存展示。
            delivery.emit = emit
            await delivery.produce()
            # 最终投影保存已在同一事务完成调度终态，失败留待原生事实检查。
            # Failure deliberately remains RUNNING. The next inspection determines
            # completed projection repair versus NEEDS_REVIEW; never blind retry.
            return True

    # 后台拥有执行生命周期；唤醒只是提示重读数据库事实，不能直接派发。
    async def run(self, stop: asyncio.Event) -> None:
        wake = self.store.wake
        wake.bind()
        loop = asyncio.get_running_loop()
        reconcile_at = loop.time()
        tasks: set[asyncio.Task[None]] = set()
        active_conversations: set[int] = set()
        cursor = 0

        async def guarded(turn: dict[str, Any]) -> None:
            try:
                if await self.dispatch(turn) is False:
                    # 退出未持锁的连接后本地退避；该槽有界占用，不篡改其他进程期限。
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=self.retry_seconds)
                    except asyncio.TimeoutError:
                        pass
            except Exception:
                _LOG.exception("Chat durable dispatch inspection failed")
                try:
                    # 异常只安排后续事实检查；终态不可回退，未知写结果不重跑。
                    current = await asyncio.to_thread(self.store.get, turn["input_message_id"])
                    if current is not None:
                        await asyncio.to_thread(
                            self.store.defer,
                            turn["input_message_id"],
                            current["dispatch_generation"],
                            self.retry_seconds,
                        )
                except Exception:
                    _LOG.exception("Chat dispatch retry scheduling failed")
            finally:
                self.active.discard(turn["input_message_id"])
                active_conversations.discard(turn["conversation_id"])
                # 释放槽后立即重查同会话后轮；BUSY/异常仍受数据库重查时间限制。
                wake.notify()

        try:
            while not stop.is_set():
                tasks.difference_update(task for task in tuple(tasks) if task.done())
                if len(tasks) >= self.max_concurrency:
                    # 满槽时外部重复唤醒留在合并信号中，不扫描、不空转。
                    stopping = asyncio.create_task(stop.wait())
                    try:
                        await asyncio.wait(tasks | {stopping}, return_when=asyncio.FIRST_COMPLETED)
                    finally:
                        stopping.cancel()
                        await asyncio.gather(stopping, return_exceptions=True)
                    continue

                # 查询前取版本：查询期间和等待切换窗口中的新通知都不会丢失。
                version = wake.snapshot()
                try:
                    await asyncio.to_thread(
                        self.store.materialize, self.messages, self.processing_tasks
                    )
                    candidates = await asyncio.to_thread(
                        self.store.candidates,
                        exclude_conversations=tuple(active_conversations),
                        limit=self.max_concurrency - len(tasks),
                        after_input_id=cursor,
                    )
                    for turn in candidates:
                        if stop.is_set():
                            break
                        if (
                            turn["input_message_id"] in self.active
                            or turn["conversation_id"] in active_conversations
                        ):
                            continue
                        cursor = turn["input_message_id"]
                        self.active.add(turn["input_message_id"])
                        active_conversations.add(turn["conversation_id"])
                        task = asyncio.create_task(guarded(turn))
                        tasks.add(task)
                        task.add_done_callback(tasks.discard)
                    # 扫描周期不因新通知顺延；到期补漏与持久化重查时间取较早者。
                    now = loop.time()
                    if now >= reconcile_at:
                        reconcile_at = now + self.reconcile_seconds
                    if len(tasks) >= self.max_concurrency:
                        continue
                    delay = await asyncio.to_thread(
                        self.store.next_delay,
                        exclude_conversations=tuple(active_conversations),
                    )
                    timeout = max(0.0, reconcile_at - loop.time())
                    if delay is not None:
                        timeout = min(timeout, delay)
                    await wake.wait_after(version, timeout, stop)
                except Exception:
                    _LOG.exception("Chat durable inbox reconciliation failed")
                    # 存储故障期间保留合并通知，按有界间隔重查，不因通知风暴忙等。
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=self.retry_seconds)
                    except asyncio.TimeoutError:
                        pass
        finally:
            # 停止不取消已派发的业务，收尾期间的新意图保留给下次启动补扫。
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            wake.close()
