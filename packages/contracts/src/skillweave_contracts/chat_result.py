"""Versioned neutral result of one native Chat turn.

This pure reducer owns public event aggregation, not model execution or product
storage. A final snapshot is recoverable without replaying tokens or tools.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal, NotRequired, TypeAlias, TypedDict, cast

# 公开事件只保存 JSON 可表达的值, 不把运行器或框架对象写进页面消息。
JsonValue: TypeAlias = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None
JsonObject: TypeAlias = dict[str, JsonValue]


# 按模型原始消息 ID 聚合文本和可见推理, 区分过程回复与最终回答。
class ModelMessageRecord(TypedDict):
    messageId: str
    sequence: int
    text: str
    reasoning: str
    phase: Literal["process", "final"]


# 生成进度使用固定阶段集合, 避免页面依赖任意工具描述文本。
GenerationStage = Literal[
    "preparing", "generating", "validating_loading", "saving", "completed", "failed"
]


# 每条进度绑定真实工具调用, 并记录阶段耗时与稳定错误码。
class GenerationProgressRecord(TypedDict):
    toolCallId: str
    name: Literal["generate_a2ui", "generate_interaction"]
    stage: GenerationStage
    elapsedMs: int
    errorCode: str


# 工具生命周期、协议状态与业务成功分别保存, 返回结果不等于业务成功。
class ToolCallRecord(TypedDict, total=False):
    toolCallId: str
    sequence: int
    name: str
    arguments: JsonObject
    lifecycleStatus: Literal["running", "returned", "raised"]
    toolMessageStatus: Literal["success", "error"] | None
    # 保留工具的真实起止时间和回执, 页面可据此解释执行过程。
    startedAt: str
    finishedAt: str
    durationMs: int
    result: JsonValue
    businessSuccess: bool | None
    errorCode: str
    generationProgress: list[GenerationProgressRecord]


# 投影绑定轮次及两条产品消息, 供刷新恢复和执行明细展示。
class ExecutionProjection(TypedDict):
    schemaVersion: Literal["v1"]
    modelMessages: list[ModelMessageRecord]
    toolCalls: list[ToolCallRecord]


# 正文片段与模型消息关联, 避免多次模型回复被拼成一个无法解释的结果。
class TextContentPart(TypedDict, total=False):
    type: Literal["text"]
    id: str
    text: str
    modelMessageId: str


# 持久化片段用卡片 ID 引用, 公开响应再补入卡片内容。
class ApplicationContentPart(TypedDict, total=False):
    type: Literal["application"]
    id: str
    cardId: str
    card: JsonObject | None


# 个人工作流注册结果作为独立内容片段, 刷新后仍能定位创建产物。
class PersonalWorkflowContentPart(TypedDict):
    type: Literal["personal_workflow"]
    id: str
    workflow: JsonObject


ContentPart: TypeAlias = TextContentPart | ApplicationContentPart | PersonalWorkflowContentPart


# 标识字段只接收有界非空字符串, 防止异常事件污染展示索引。
def _identifier(value: object, *, limit: int = 256) -> str | None:
    return value if isinstance(value, str) and 0 < len(value) <= limit else None


class ChatTurnResult(TypedDict):
    schemaVersion: Literal["v1"]
    turnId: str
    content: dict[str, Any]
    finalModelMessageId: str | None
    eventCount: int
    checksum: str
    terminal: dict[str, Any]


class RuntimeTurnInspection(TypedDict):
    status: Literal["NOT_STARTED", "BUSY", "COMPLETED", "NEEDS_REVIEW"]
    result: NotRequired[ChatTurnResult]


class ChatResultAccumulator:
    """Pure accumulation of the public application protocol in arrival order."""

    def __init__(self, *, turn_id: str, text_part_prefix: str = "text") -> None:
        self.turn_id = turn_id
        self.text_part_prefix = text_part_prefix
        self.execution: ExecutionProjection = {
            "schemaVersion": "v1",
            "modelMessages": [],
            "toolCalls": [],
        }
        self.content: dict[str, Any] = {
            "text": "",
            "reasoning": "",
            "tools": [],
            "events": [],
            "delivery": "running",
            "execution": self.execution,
            "parts": [],
        }
        self.parts: list[ContentPart] = self.content["parts"]
        self._live_cards: dict[str, JsonObject] = {}
        self._text_part_count = 0
        self._model_messages: dict[str, ModelMessageRecord] = {}
        self._tool_calls: dict[str, ToolCallRecord] = {}
        self.final_model_message_id: str | None = None
        self.sequence = 0
        self.completed = False
        self.failed = False
        self.waiting = False
        self.done: dict[str, Any] | None = None
        self.integrity_errors: list[str] = []

    def _model_delta(
        self,
        event: dict[str, Any],
        key: Literal["text", "reasoning"],
        sequence: int,
    ) -> str | None:
        # 文本增量按原始模型消息身份聚合, 非法文本事件不进入展示。
        message_id = _identifier(event.get("modelMessageId"))
        value = event.get("text")
        if not isinstance(value, str):
            return None
        # 首次见到模型消息时保存序号, 后续文本和推理追加到同一记录。
        if message_id is not None:
            record = self._model_messages.get(message_id)
            if record is None:
                record = {
                    "messageId": message_id,
                    "sequence": sequence,
                    "text": "",
                    "reasoning": "",
                    "phase": "process",
                }
                self._model_messages[message_id] = record
                self.execution["modelMessages"].append(record)
            # 正文与可见推理分开累计, 推理不混入对话正文片段。
            if key == "text":
                record["text"] += value
            else:
                record["reasoning"] += value
        if key == "reasoning" and message_id is None:
            # 无供应商消息身份时保留原始可见推理, 不编造一个模型消息 ID。
            self.content["unattributedReasoning"] = (
                self.content.get("unattributedReasoning", "") + value
            )
            self.content["reasoning"] = self.content["unattributedReasoning"]
        if key != "text":
            return None
        # 仅相邻且属于同一模型消息的正文片段可合并。
        current = self.parts[-1] if self.parts else None
        current_model_id = (
            current.get("modelMessageId")
            if isinstance(current, dict) and current.get("type") == "text"
            else None
        )
        if (
            isinstance(current, dict)
            and current.get("type") == "text"
            and current_model_id == message_id
        ):
            # 复用已有正文片段 ID, 使前端增量与刷新后的内容定位一致。
            text_part = cast(TextContentPart, current)
            text_part["text"] = text_part["text"] + value
            return text_part["id"]
        return self._append_text_part(value, message_id)

    def _append_text_part(self, value: str, message_id: str | None) -> str:
        # 片段 ID 由助手消息和本地计数组成, 不冒充模型原始消息 ID。
        self._text_part_count += 1
        part: TextContentPart = {
            "type": "text",
            "id": f"{self.text_part_prefix}:{self._text_part_count}",
            "text": value,
        }
        # 有原始模型身份才记录关联, 没有时保持缺省。
        if message_id is not None:
            part["modelMessageId"] = message_id
        self.parts.append(part)
        return part["id"]

    # 卡片事件先检查结构和标识, 再更新当前轮的实时卡片索引。
    def _application(self, event: dict[str, Any]) -> tuple[str, JsonObject] | None:
        card = event.get("card")
        if not isinstance(card, dict):
            return None
        card_id = _identifier(card.get("cardId"), limit=128)
        if card_id is None:
            return None
        # 拷贝卡片快照避免外部修改; 同一卡片只创建一个内容片段。
        copied = cast(JsonObject, copy.deepcopy(card))
        self._live_cards[card_id] = copied
        part_id = "application:" + card_id
        # 卡片重复更新替换快照, 不重复插入页面位置。
        if not any(part.get("id") == part_id for part in self.parts):
            self.parts.append(
                {
                    "type": "application",
                    "id": part_id,
                    "cardId": card_id,
                }
            )
        return part_id, copied

    # 个人工作流展示只接受已注册个人资产的结果, 不接受任意类型伪装。
    def _personal_workflow(self, event: dict[str, Any]) -> tuple[str, JsonObject]:
        workflow = event.get("workflow")
        if not isinstance(workflow, dict):
            raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
        key = _identifier(workflow.get("definitionKey"))
        # 校验个人资产前缀与来源, 防止预制资产被误展示为个人产物。
        if (
            key is None
            or not key.startswith("personal-wf-")
            or workflow.get("source") != "PERSONAL"
        ):
            raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
        if (
            # 名称与默认需求都有长度上限, 保护页面和历史持久化大小。
            not isinstance(workflow.get("name"), str)
            or not workflow["name"].strip()
            or len(workflow["name"]) > 200
            or not isinstance(workflow.get("defaultRequirement"), str)
            or len(workflow["defaultRequirement"]) > 2000
        ):
            raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
        # 节点数受限, 且仅允许技能和业务能力两种已支持类型。
        nodes = workflow.get("nodes")
        if not isinstance(nodes, list) or not 1 <= len(nodes) <= 8:
            raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
        public_nodes: list[JsonValue] = []
        for node in nodes:
            if not isinstance(node, dict) or node.get("type") not in {
                "SKILL",
                "BUSINESS_CAPABILITY",
            }:
                raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
            # 按节点类型选择对应资产引用, 并验证节点及引用身份。
            reference = "skillKey" if node["type"] == "SKILL" else "abilityKey"
            if _identifier(node.get("nodeId")) is None or _identifier(node.get(reference)) is None:
                raise ValueError("INVALID_PERSONAL_WORKFLOW_EVENT")
            # 只复制公开的节点概要字段, 不把内部编排参数整包投影到页面。
            public_node = {field: node[field] for field in ("nodeId", "type", reference)}
            if isinstance(node.get("displayName"), str):
                public_node["displayName"] = node["displayName"]
            public_nodes.append(public_node)
        # 创建结果保留名称、默认需求和步骤, 作为稳定的个人工作流卡片。
        copied: JsonObject = {
            "definitionKey": key,
            "source": "PERSONAL",
            "name": workflow["name"],
            "defaultRequirement": workflow["defaultRequirement"],
            "nodes": public_nodes,
        }
        # 可选输入契约深拷贝保存, 后续运行仍由执行服务校验。
        if isinstance(workflow.get("inputSchema"), dict):
            copied["inputSchema"] = copy.deepcopy(workflow["inputSchema"])
        part_id = "personal-workflow:" + key
        # 同一资产重复事件必须内容一致, 不一致则明确暴露冲突。
        existing = next((part for part in self.parts if part.get("id") == part_id), None)
        if existing is not None:
            if existing.get("workflow") != copied:
                raise ValueError("PERSONAL_WORKFLOW_EVENT_CONFLICT")
        else:
            self.parts.append({"type": "personal_workflow", "id": part_id, "workflow": copied})
        return part_id, copied

    # 返回独立快照, 并按卡片引用补齐实时内容, 避免修改持久化对象。
    def _public_content(self) -> dict[str, Any]:
        content = copy.deepcopy(self.content)
        for part in content["parts"]:
            if part.get("type") == "application":
                part["card"] = copy.deepcopy(self._live_cards.get(part["cardId"]))
        return content

    # 工具开始事件必须具备真实调用号、名称、起始时间和参数对象。
    def _tool_started(self, event: dict[str, Any], sequence: int) -> None:
        tool_call_id = _identifier(event.get("toolCallId"))
        name = _identifier(event.get("name"), limit=128)
        started_at = _identifier(event.get("startedAt"), limit=64)
        arguments = event.get("arguments")
        if (
            tool_call_id is None
            or name is None
            or started_at is None
            or not isinstance(arguments, dict)
        ):
            return
        # 初始状态只表示正在执行, 业务成功与工具消息状态尚未得到确认。
        record: ToolCallRecord = {
            "toolCallId": tool_call_id,
            "sequence": sequence,
            "name": name,
            "arguments": cast(JsonObject, copy.deepcopy(arguments)),
            "lifecycleStatus": "running",
            "toolMessageStatus": None,
            "startedAt": started_at,
        }
        # 保存调用索引并按出现顺序加入执行明细。
        self._tool_calls[tool_call_id] = record
        self.execution["toolCalls"].append(record)

    # 结束事件独立检查时间、耗时和枚举值, 不能靠真假值推断成功。
    def _tool_finished(self, event: dict[str, Any], sequence: int) -> None:
        tool_call_id = _identifier(event.get("toolCallId"))
        name = _identifier(event.get("name"), limit=128)
        started_at = _identifier(event.get("startedAt"), limit=64)
        finished_at = _identifier(event.get("finishedAt"), limit=64)
        # 耗时必须是非负整数; 工具返回、抛错和业务结果分别表达。
        duration_ms = event.get("durationMs")
        lifecycle = event.get("lifecycleStatus")
        tool_status = event.get("toolMessageStatus")
        if (
            tool_call_id is None
            or name is None
            or started_at is None
            or finished_at is None
            or type(duration_ms) is not int
            or duration_ms < 0
            or lifecycle not in {"returned", "raised"}
            or tool_status not in {None, "success", "error"}
        ):
            return
        # 缺少开始事件时仍保存真实结束事实, 但不虚构原始调用参数。
        record = self._tool_calls.get(tool_call_id)
        if record is None:
            record = {
                "toolCallId": tool_call_id,
                "sequence": sequence,
                "name": name,
                "arguments": {},
                "lifecycleStatus": "running",
                "toolMessageStatus": None,
                "startedAt": started_at,
            }
            # 结束事件可补齐缺失的开始记录, 索引与展示列表保持同一对象。
            self._tool_calls[tool_call_id] = record
            self.execution["toolCalls"].append(record)
        # 仅在结束事件校验通过后更新生命周期和耗时。
        record.update(
            {
                "lifecycleStatus": lifecycle,
                "toolMessageStatus": tool_status,
                "finishedAt": finished_at,
                "durationMs": duration_ms,
            }
        )
        # 保留实际存在的结果字段, 区分没有结果与结果为空。
        if "result" in event:
            record["result"] = cast(JsonValue, copy.deepcopy(event["result"]))
        # 业务成功只接受布尔或未知, 不能将字符串 true 当作成功。
        business_success = event.get("businessSuccess")
        if (
            type(business_success) is bool or business_success is None
        ) and "businessSuccess" in event:
            record["businessSuccess"] = business_success
        # 错误码限定长度, 避免任意异常对象混进历史。
        error_code = _identifier(event.get("errorCode"), limit=128)
        if error_code is not None:
            record["errorCode"] = error_code

    # 生成进度只能追加到已有且同名的生成工具调用。
    def _generation_progress(self, event: dict[str, Any]) -> GenerationProgressRecord | None:
        tool_call_id = _identifier(event.get("toolCallId"))
        record = self._tool_calls.get(tool_call_id or "")
        # 校验阶段、耗时和错误码格式, 忽略不能安全解释的进度事件。
        stage = event.get("stage")
        elapsed = event.get("elapsedMs")
        code = event.get("errorCode", "")
        if (
            record is None
            or record["name"] not in {"generate_a2ui", "generate_interaction"}
            or event.get("name") != record["name"]
            or not isinstance(stage, str)
            or stage
            not in {
                "preparing",
                "generating",
                "validating_loading",
                "saving",
                "completed",
                "failed",
            }
            or type(elapsed) is not int
            or elapsed < 0
            or not isinstance(code, str)
            or len(code) > 128
            or (code and not all(char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for char in code))
        ):
            return None
        # 阶段严格前进且耗时不回退, 最多保存五个阶段。
        progress = record.setdefault("generationProgress", [])
        order = {
            "preparing": 0,
            "generating": 1,
            "validating_loading": 2,
            "saving": 3,
            "completed": 4,
            "failed": 4,
        }
        # 重复、倒退或过量进度不继续累积, 避免历史膨胀。
        if len(progress) >= 5 or (
            progress
            and (
                order[stage] <= order[progress[-1]["stage"]] or elapsed < progress[-1]["elapsedMs"]
            )
        ):
            return None
        # 校验后保存固定结构, 前端无需从工具文本猜测进展。
        value: GenerationProgressRecord = {
            "toolCallId": record["toolCallId"],
            "name": cast(Literal["generate_a2ui", "generate_interaction"], record["name"]),
            "stage": cast(GenerationStage, stage),
            "elapsedMs": elapsed,
            "errorCode": code,
        }
        if not progress or progress[-1] != value:
            progress.append(value)
        return value

    # 最终消息身份取自执行事件, 不把最后一段工具前文本误当总结。
    def _finalize_model_messages(self, event: dict[str, Any]) -> None:
        final_id = _identifier(event.get("finalModelMessageId"))
        self.final_model_message_id = final_id
        final_content = event.get("content")
        # 有原始最终身份时标记对应记录; 必要时补建仅含真实结果的记录。
        if final_id is not None:
            record = self._model_messages.get(final_id)
            if record is None:
                record = {
                    "messageId": final_id,
                    "sequence": self.sequence,
                    "text": "",
                    "reasoning": "",
                    "phase": "final",
                }
                self._model_messages[final_id] = record
                self.execution["modelMessages"].append(record)
            # 已有流式正文优先, 终态文本仅用于补齐没有增量的回答。
            record["phase"] = "final"
            if not record["text"] and isinstance(final_content, str):
                record["text"] = final_content
            self.content["text"] = record["text"]
            self.content["reasoning"] = record["reasoning"]
        elif isinstance(final_content, str):
            # A provider without native ids still gets an accurate final answer,
            # but no synthetic model message identity is invented.
            self.content["text"] = final_content
        # 检查最终正文是否已流式展示, 避免终态响应再重复追加一遍。
        matching_text = "".join(
            str(part.get("text", ""))
            for part in self.parts
            if part.get("type") == "text"
            and (
                part.get("modelMessageId") == final_id
                if final_id is not None
                else "modelMessageId" not in part
            )
        )
        # 无原始 ID 时要求全文相同才认定已展示, 不人为编造模型身份。
        has_streamed_final = (
            bool(matching_text)
            if final_id is not None
            else isinstance(final_content, str) and matching_text == final_content
        )
        # 供应商只在终态给出正文时, 把该真实正文追加一次。
        if isinstance(final_content, str) and final_content and not has_streamed_final:
            # Some providers only expose the final text on their terminal
            # message. Add that real text once; streamed text remains
            # authoritative whenever a matching part already exists.
            self._append_text_part(final_content, final_id)

    def consume(self, event: Mapping[str, Any]) -> dict[str, Any] | None:
        """Fold one event; return the normalized public event, never perform IO."""
        if self.completed:
            raise ValueError("CHAT_RESULT_EVENT_AFTER_DONE")
        item = copy.deepcopy(dict(event))
        kind = item.get("type")
        if kind in {"text_delta", "reasoning_delta"} and not isinstance(item.get("text"), str):
            self.integrity_errors.append("INVALID_MODEL_DELTA")
        if kind == "tool_call_started" and (
            _identifier(item.get("toolCallId")) is None
            or _identifier(item.get("name"), limit=128) is None
            or _identifier(item.get("startedAt"), limit=64) is None
            or not isinstance(item.get("arguments"), dict)
        ):
            self.integrity_errors.append("INVALID_TOOL_START")
        if kind == "tool_call_finished" and (
            _identifier(item.get("toolCallId")) is None
            or _identifier(item.get("name"), limit=128) is None
            or _identifier(item.get("startedAt"), limit=64) is None
            or _identifier(item.get("finishedAt"), limit=64) is None
            or type(item.get("durationMs")) is not int
            or item["durationMs"] < 0
            or item.get("lifecycleStatus") not in {"returned", "raised"}
            or item.get("toolMessageStatus") not in {None, "success", "error"}
        ):
            self.integrity_errors.append("INVALID_TOOL_FINISH")
        self.sequence += 1
        if kind == "done":
            self._finalize_model_messages(item)
            self.done = item
            self.completed = True
            return None
        if kind == "error":
            self.failed = True
            self.content["errorCode"] = item.get("code", "CHAT_UNAVAILABLE")
            return None
        if kind == "waiting_action":
            self.waiting = True
            card_id = _identifier(item.get("cardId"), limit=128)
            if card_id is not None:
                item["partId"] = "application:" + card_id
            self.content["events"].append(item)
        elif kind in ("text_delta", "reasoning_delta"):
            key: Literal["text", "reasoning"] = "text" if kind == "text_delta" else "reasoning"
            part_id = self._model_delta(item, key, self.sequence)
            if part_id is not None:
                item["partId"] = part_id
        elif kind == "tool_call":
            self.content["tools"].append(str(item.get("tool", "")))
        elif kind == "tool_call_started":
            self._tool_started(item, self.sequence)
        elif kind == "tool_call_finished":
            prior = self._tool_calls.get(str(item.get("toolCallId", "")))
            if prior is not None and (
                prior.get("name") != item.get("name")
                or prior.get("startedAt") != item.get("startedAt")
                or prior.get("lifecycleStatus") != "running"
            ):
                self.integrity_errors.append("TOOL_LIFECYCLE_CONFLICT")
            self._tool_finished(item, self.sequence)
        elif kind == "a2ui_generation_progress":
            progress = self._generation_progress(item)
            if progress is None:
                return None
            item = {"type": kind, **progress}
        elif kind == "application_rendered":
            application = self._application(item)
            if application is None:
                raise ValueError("INVALID_APPLICATION_EVENT")
            part_id, card = application
            item = {**item, "partId": part_id, "card": card}
            self.content["events"].append(
                {
                    "type": kind,
                    "partId": part_id,
                    "cardId": card["cardId"],
                }
            )
        elif kind == "personal_workflow_created":
            part_id, workflow = self._personal_workflow(item)
            item = {
                "type": kind,
                "partId": part_id,
                "workflow": workflow,
                "sequence": self.sequence,
            }
            if not any(
                e.get("type") == kind and e.get("partId") == part_id for e in self.content["events"]
            ):
                self.content["events"].append(copy.deepcopy(item))
        elif kind in ("workflow_confirm", "interaction_required"):
            self.content["events"].append(item)
        else:
            return None
        return item

    def finish(self) -> ChatTurnResult:
        """Require a real terminal fact; waiting is not business completion."""
        if not self.completed or self.failed or self.done is None or self.integrity_errors:
            raise ValueError("TURN_COMPLETION_EVIDENCE_MISSING")
        self.content["delivery"] = "waiting_action" if self.waiting else "completed"
        content = self._public_content()
        result: ChatTurnResult = {
            "schemaVersion": "v1",
            "turnId": self.turn_id,
            "content": content,
            "finalModelMessageId": self.final_model_message_id,
            "eventCount": self.sequence,
            "checksum": "",
            "terminal": copy.deepcopy(self.done),
        }
        result["checksum"] = _checksum(result)
        return validate_result(result)


def _checksum(result: Mapping[str, Any]) -> str:
    body = {key: value for key, value in result.items() if key != "checksum"}
    return hashlib.sha256(
        json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def result_from_events(events: Sequence[Mapping[str, Any]], *, turn_id: str) -> ChatTurnResult:
    accumulator = ChatResultAccumulator(turn_id=turn_id)
    for event in events:
        accumulator.consume(event)
    return accumulator.finish()


def validate_result(value: object) -> ChatTurnResult:
    """Reject incomplete/corrupt snapshots even when a caller recomputes a hash."""
    if not isinstance(value, dict) or value.get("schemaVersion") != "v1":
        raise ValueError("CHAT_RESULT_VERSION_INVALID")
    if set(value) != {
        "schemaVersion",
        "turnId",
        "content",
        "finalModelMessageId",
        "eventCount",
        "checksum",
        "terminal",
    }:
        raise ValueError("CHAT_RESULT_FIELDS_INVALID")
    if _identifier(value.get("turnId")) is None:
        raise ValueError("CHAT_RESULT_TURN_ID_INVALID")
    if type(value.get("eventCount")) is not int or value["eventCount"] < 1:
        raise ValueError("CHAT_RESULT_COMPLETION_MISSING")
    if value.get("checksum") != _checksum(value):
        raise ValueError("CHAT_RESULT_CHECKSUM_MISMATCH")
    terminal = value.get("terminal")
    if not isinstance(terminal, dict) or terminal.get("type") != "done":
        raise ValueError("CHAT_RESULT_COMPLETION_MISSING")
    if terminal.get("finalModelMessageId") != value.get("finalModelMessageId"):
        raise ValueError("CHAT_RESULT_FINAL_MODEL_CONFLICT")
    content = value.get("content")
    if not isinstance(content, dict) or content.get("delivery") not in {
        "completed",
        "waiting_action",
    }:
        raise ValueError("CHAT_RESULT_TERMINAL_INVALID")
    if (
        "errorCode" in content
        or not all(isinstance(content.get(key), str) for key in ("text", "reasoning"))
        or (
            "unattributedReasoning" in content
            and not isinstance(content["unattributedReasoning"], str)
        )
    ):
        raise ValueError("CHAT_RESULT_CONTENT_INVALID")
    if not isinstance(content.get("tools"), list) or not all(
        isinstance(v, str) for v in content["tools"]
    ):
        raise ValueError("CHAT_RESULT_TOOLS_INVALID")
    execution = content.get("execution")
    if not isinstance(execution, dict) or execution.get("schemaVersion") != "v1":
        raise ValueError("CHAT_RESULT_EXECUTION_INVALID")
    models, calls = execution.get("modelMessages"), execution.get("toolCalls")
    if not isinstance(models, list) or not isinstance(calls, list):
        raise ValueError("CHAT_RESULT_EXECUTION_INVALID")
    model_ids: set[str] = set()
    previous_sequence = 0
    for model in models:
        if (
            not isinstance(model, dict)
            or _identifier(model.get("messageId")) is None
            or model["messageId"] in model_ids
            or type(model.get("sequence")) is not int
            or not previous_sequence < model["sequence"] <= value["eventCount"]
            or model.get("phase") not in {"process", "final"}
            or not all(isinstance(model.get(key), str) for key in ("text", "reasoning"))
        ):
            raise ValueError("CHAT_RESULT_MODEL_INVALID")
        model_ids.add(model["messageId"])
        previous_sequence = model["sequence"]
    final_id = value.get("finalModelMessageId")
    if final_id is not None and (_identifier(final_id) is None or final_id not in model_ids):
        raise ValueError("CHAT_RESULT_FINAL_MODEL_MISSING")
    finals = [m for m in models if m["phase"] == "final"]
    if final_id is not None and (
        len(finals) != 1
        or finals[0]["messageId"] != final_id
        or finals[0]["text"] != content["text"]
        or finals[0]["reasoning"] != content["reasoning"]
    ):
        raise ValueError("CHAT_RESULT_FINAL_MODEL_CONFLICT")
    if isinstance(terminal.get("content"), str) and terminal["content"] != content["text"]:
        raise ValueError("CHAT_RESULT_FINAL_TEXT_CONFLICT")
    if final_id is None and finals:
        raise ValueError("CHAT_RESULT_FINAL_MODEL_CONFLICT")
    call_ids: set[str] = set()
    previous_sequence = 0
    for call in calls:
        if (
            not isinstance(call, dict)
            or _identifier(call.get("toolCallId")) is None
            or call["toolCallId"] in call_ids
            or _identifier(call.get("name"), limit=128) is None
            or not isinstance(call.get("arguments"), dict)
            or call.get("lifecycleStatus") not in {"returned", "raised"}
            or call.get("toolMessageStatus") not in {None, "success", "error"}
            or type(call.get("sequence")) is not int
            or not previous_sequence < call["sequence"] <= value["eventCount"]
            or type(call.get("durationMs")) is not int
            or call["durationMs"] < 0
            or _identifier(call.get("startedAt"), limit=64) is None
            or _identifier(call.get("finishedAt"), limit=64) is None
        ):
            raise ValueError("CHAT_RESULT_TOOL_INCOMPLETE")
        if (
            "businessSuccess" in call
            and call["businessSuccess"] is not None
            and type(call["businessSuccess"]) is not bool
        ):
            raise ValueError("CHAT_RESULT_TOOL_INVALID")
        progress = call.get("generationProgress", [])
        if not isinstance(progress, list) or len(progress) > 5:
            raise ValueError("CHAT_RESULT_PROGRESS_INVALID")
        previous_stage, previous_elapsed = -1, -1
        stages = {
            "preparing": 0,
            "generating": 1,
            "validating_loading": 2,
            "saving": 3,
            "completed": 4,
            "failed": 4,
        }
        for item in progress:
            if (
                not isinstance(item, dict)
                or call["name"] not in {"generate_a2ui", "generate_interaction"}
                or item.get("name") != call["name"]
                or item.get("toolCallId") != call["toolCallId"]
                or not isinstance(item.get("stage"), str)
                or item["stage"] not in stages
                or stages[item["stage"]] <= previous_stage
                or type(item.get("elapsedMs")) is not int
                or item["elapsedMs"] < previous_elapsed
                or item["elapsedMs"] < 0
                or not isinstance(item.get("errorCode"), str)
                or len(item["errorCode"]) > 128
                or any(
                    char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
                    for char in item["errorCode"]
                )
            ):
                raise ValueError("CHAT_RESULT_PROGRESS_INVALID")
            previous_stage, previous_elapsed = stages[item["stage"]], item["elapsedMs"]
        call_ids.add(call["toolCallId"])
        previous_sequence = call["sequence"]
    parts, events = content.get("parts"), content.get("events")
    if not isinstance(parts, list) or not isinstance(events, list):
        raise ValueError("CHAT_RESULT_PARTS_INVALID")
    part_ids: set[str] = set()
    card_ids: set[str] = set()
    checker = ChatResultAccumulator(turn_id=value["turnId"])
    for part in parts:
        if (
            not isinstance(part, dict)
            or _identifier(part.get("id"), limit=512) is None
            or part["id"] in part_ids
        ):
            raise ValueError("CHAT_RESULT_PARTS_INVALID")
        part_ids.add(part["id"])
        if part.get("type") == "text":
            if not isinstance(part.get("text"), str) or (
                "modelMessageId" in part and part["modelMessageId"] not in model_ids
            ):
                raise ValueError("CHAT_RESULT_TEXT_INVALID")
        elif part.get("type") == "application":
            card = part.get("card")
            if (
                not isinstance(card, dict)
                or _identifier(part.get("cardId"), limit=128) is None
                or card.get("cardId") != part["cardId"]
                or part["id"] != "application:" + part["cardId"]
            ):
                raise ValueError("CHAT_RESULT_CARD_MISSING")
            card_ids.add(part["cardId"])
        elif part.get("type") == "personal_workflow":
            checked_id, workflow = checker._personal_workflow({"workflow": part.get("workflow")})
            if checked_id != part["id"] or workflow != part.get("workflow"):
                raise ValueError("CHAT_RESULT_WORKFLOW_INVALID")
        else:
            raise ValueError("CHAT_RESULT_PART_TYPE_INVALID")
    # 模型正文与有序页面片段必须一致, 不能只校验 ID 存在。
    for model in models:
        text = "".join(
            part["text"]
            for part in parts
            if part.get("type") == "text" and part.get("modelMessageId") == model["messageId"]
        )
        if text != model["text"]:
            raise ValueError("CHAT_RESULT_MODEL_PARTS_CONFLICT")
    if final_id is None and content["text"]:
        anonymous_parts = [
            part["text"]
            for part in parts
            if part.get("type") == "text" and "modelMessageId" not in part
        ]
        if not anonymous_parts or (
            "".join(anonymous_parts) != content["text"] and anonymous_parts[-1] != content["text"]
        ):
            raise ValueError("CHAT_RESULT_FINAL_PART_MISSING")
    waiting = False
    rendered_cards: set[str] = set()
    workflow_parts = {
        part["id"]: part["workflow"] for part in parts if part.get("type") == "personal_workflow"
    }
    workflow_events: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("CHAT_RESULT_EVENT_INVALID")
        kind = event.get("type")
        if kind == "waiting_action":
            waiting = True
            if event.get("cardId") not in card_ids or event.get("partId") != "application:" + str(
                event.get("cardId")
            ):
                raise ValueError("CHAT_RESULT_WAITING_CARD_MISSING")
        elif kind == "application_rendered":
            if event.get("cardId") not in card_ids or event.get("partId") != "application:" + str(
                event.get("cardId")
            ):
                raise ValueError("CHAT_RESULT_CARD_EVENT_MISSING")
            rendered_cards.add(event["cardId"])
        elif kind == "personal_workflow_created":
            if (
                event.get("partId") not in workflow_parts
                or event.get("workflow") != workflow_parts[event["partId"]]
            ):
                raise ValueError("CHAT_RESULT_WORKFLOW_EVENT_MISSING")
            workflow_events.add(event["partId"])
        elif kind not in {"workflow_confirm", "interaction_required"}:
            raise ValueError("CHAT_RESULT_EVENT_INVALID")
    if rendered_cards != card_ids or workflow_events != set(workflow_parts):
        raise ValueError("CHAT_RESULT_PART_EVENT_MISSING")
    if waiting != (content["delivery"] == "waiting_action"):
        raise ValueError("CHAT_RESULT_WAITING_CONFLICT")
    return cast(ChatTurnResult, copy.deepcopy(value))
