"""Durable display projection of one native agent turn, not model history.

An HTTP subscriber may leave; the producer still consumes the native runner and
saves its outcome. Neither disconnect nor a GET retries model or tool execution.
Process crashes can leave RUNNING: this module deliberately does not guess success.
"""

import asyncio
import copy
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal, NotRequired, Protocol, TypeAlias, TypedDict, cast

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from .chat_runner import ChatStream
from .persistence_types import MessageRecord
from .processing_tasks import ProcessingContext


# 展示投影只要求更新消息, 普通仓库与带执行代际隔离的写入器都实现此接口。
class MessageProjection(Protocol):
    """Both direct messages and generation-fenced writes persist projections."""

    def update_delivery(
        self, *, conversation_id: int, message_id: int, content: dict[str, Any]
    ) -> None: ...


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
    turnId: str
    inputMessageId: str
    assistantMessageId: str
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


# 运行参数固定绑定用户、会话及轮次, 引用和处理上下文仅按需传入。
class RunnerArguments(TypedDict):
    user_id: int
    conversation_id: int
    text: str
    turn_id: str
    run_references: NotRequired[Sequence[Mapping[str, Any]]]
    processing_context: NotRequired[ProcessingContext]


# 此类消费执行事件并保存展示, 不拥有模型工具循环, 也不决定业务重试。
class ChatDelivery:
    def __init__(
        self,
        *,
        messages: MessageProjection,
        runner: ChatStream,
        user_id: int,
        conversation_id: int,
        text: str,
        input_message: MessageRecord,
        assistant_message: MessageRecord,
        run_references: tuple[dict[str, Any], ...] = (),
        processing_context: ProcessingContext | None = None,
    ) -> None:
        self.messages, self.runner = messages, runner
        self.user_id, self.conversation_id, self.text = user_id, conversation_id, text
        self.input_id, self.assistant_id = input_message["id"], assistant_message["id"]
        # 深拷贝引用与处理上下文, 避免外部对象修改已接受轮次的输入。
        self.run_references = copy.deepcopy(list(run_references))
        self.processing_context = copy.deepcopy(processing_context)
        self.turn_id = str(self.input_id)
        # 执行明细独立保存模型消息和工具调用, 保留它们与产品消息的关联。
        self.execution: ExecutionProjection = {
            "schemaVersion": "v1",
            "turnId": self.turn_id,
            "inputMessageId": str(self.input_id),
            "assistantMessageId": str(self.assistant_id),
            "modelMessages": [],
            "toolCalls": [],
        }
        # 展示从运行中开始, 只有完整消费原生迭代器后才写入结束状态。
        self.content: dict[str, Any] = {
            "text": "",
            "reasoning": "",
            "tools": [],
            "events": [],
            "delivery": "running",
            "execution": self.execution,
            "parts": [],
        }
        # 卡片续聊沿用原消息中的恢复来源, 不因重建投影而丢失关联。
        if isinstance(assistant_message.get("content", {}).get("continuation"), dict):
            self.content["continuation"] = copy.deepcopy(
                assistant_message["content"]["continuation"]
            )
        if self.processing_context is not None:
            self.content["processingTaskId"] = self.processing_context["taskId"]
        # 分别索引内容片段、模型消息和工具调用, 按稳定 ID 合并后续增量。
        self.parts: list[ContentPart] = self.content["parts"]
        self._live_cards: dict[str, JsonObject] = {}
        self._text_part_count = 0
        self._model_messages: dict[str, ModelMessageRecord] = {}
        self._tool_calls: dict[str, ToolCallRecord] = {}
        self.final_model_message_id: str | None = None
        # 限制实时订阅队列长度; 持久化调度可以替换为事件日志接收器。
        self.pending: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(
            maxsize=64,
        )
        self.detached = False
        self.sequence = 0
        # Native delivery and durable journaling supply the same explicit event sink.
        self.emit: Callable[[dict[str, Any]], Awaitable[None]] = self._emit

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
            "id": f"text:{self.assistant_id}:{self._text_part_count}",
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
        if type(business_success) is bool or business_success is None:
            if "businessSuccess" in event:
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
                    "sequence": self.sequence + 1,
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

    # 实时事件附上单调序号和产品消息身份, 断开订阅后停止入队。
    async def _emit(self, event: dict[str, Any]) -> None:
        self.sequence += 1
        if not self.detached:
            await self.pending.put(
                {
                    **event,
                    "sequence": self.sequence,
                    "messageId": str(self.assistant_id),
                    "inputMessageId": str(self.input_id),
                }
            )

    # 保存展示副本; 底层写入器可额外验证当前执行代际。
    async def save(self) -> None:
        await asyncio.to_thread(
            self.messages.update_delivery,
            conversation_id=self.conversation_id,
            message_id=self.assistant_id,
            content=copy.deepcopy(self.content),
        )

    async def produce(self) -> None:
        # 完成、错误和等待交互分别追踪, 等待用户不代表整项业务已完成。
        completed, failed, waiting = False, False, False
        # 用单调时钟控制投影保存频率, 避免系统时间调整影响刷新。
        last_save = time.monotonic()
        iterator = None
        try:
            # 先发轮次开始事件, 附上处理任务关系方便页面关联。
            await self.emit(
                {
                    "type": "turn_started",
                    "turnId": self.turn_id,
                    **(
                        {"processingTaskId": self.processing_context["taskId"]}
                        if self.processing_context is not None
                        else {}
                    ),
                }
            )
            # 原始输入消息 ID 用作稳定轮次 ID, 重复投影不生成新执行身份。
            arguments: RunnerArguments = dict(
                user_id=self.user_id,
                conversation_id=self.conversation_id,
                text=self.text,
                turn_id=str(self.input_id),
            )
            # 仅传入已保存的引用和处理上下文, 不重新从客户端补取内容。
            if self.run_references:
                arguments["run_references"] = self.run_references
            if self.processing_context is not None:
                arguments["processing_context"] = self.processing_context
            # 迭代执行层输出; 这里既可消费真实执行, 也可消费已完成事件回放。
            iterator = self.runner.iterate(**arguments)
            async for event in iterator:
                kind = event.get("type")
                # 看到 done 先记录事实, 仍需等原生会话退出后才能宣布本次投影成功。
                if kind == "done":
                    self._finalize_model_messages(event)
                    completed = True
                    continue  # Native iterator/session must exit before success.
                # 保留执行错误, 即便后来出现 done 也不能覆盖为正常成功。
                if kind == "error":
                    failed = True
                    self.content["errorCode"] = event.get("code", "CHAT_UNAVAILABLE")
                    continue
                # 等待交互事件补齐产品消息身份, 定位到对应卡片片段。
                if kind == "waiting_action":
                    waiting = True
                    event = {
                        **event,
                        "turnId": self.turn_id,
                        "inputMessageId": str(self.input_id),
                        "assistantMessageId": str(self.assistant_id),
                    }
                    card_id = _identifier(event.get("cardId"), limit=128)
                    if card_id is not None:
                        event["partId"] = "application:" + card_id
                    self.content["events"].append(event)
                # 正文和推理分别聚合, 只有正文片段需要页面位置 ID。
                elif kind in ("text_delta", "reasoning_delta"):
                    key: Literal["text", "reasoning"] = (
                        "text" if kind == "text_delta" else "reasoning"
                    )
                    part_id = self._model_delta(event, key, self.sequence + 1)
                    if part_id is not None:
                        event = {**event, "partId": part_id}
                # 工具名概要与完整开始、结束事件分开处理, 兼容不同粒度的观察。
                elif kind == "tool_call":
                    self.content["tools"].append(str(event.get("tool", "")))
                elif kind == "tool_call_started":
                    self._tool_started(event, self.sequence + 1)
                elif kind == "tool_call_finished":
                    self._tool_finished(event, self.sequence + 1)
                # 不合法的生成进度直接忽略, 不向页面传播不一致阶段。
                elif kind == "a2ui_generation_progress":
                    progress = self._generation_progress(event)
                    if progress is None:
                        continue
                    event = {"type": kind, **progress}
                # 卡片展示事件绑定当前轮次, 并保存稳定引用而非重复嵌套快照。
                elif kind == "application_rendered":
                    event = {
                        **event,
                        "turnId": self.turn_id,
                        "inputMessageId": str(self.input_id),
                        "assistantMessageId": str(self.assistant_id),
                    }
                    # 校验卡片后才公开该事件, 坏卡片不占据内容片段。
                    application = self._application(event)
                    if application is None:
                        continue
                    part_id, card = application
                    event = {**event, "partId": part_id, "card": card}
                    # 历史只保存卡片身份和片段关系, 恢复时再读取权威卡片。
                    self.content["events"].append(
                        {
                            "type": "application_rendered",
                            "turnId": self.turn_id,
                            "inputMessageId": str(self.input_id),
                            "assistantMessageId": str(self.assistant_id),
                            "partId": part_id,
                            "cardId": card["cardId"],
                        }
                    )
                # 注册结果作为独立产物保存, 不能因后续模型失败而丢失已创建工作流。
                elif kind == "personal_workflow_created":
                    part_id, workflow = self._personal_workflow(event)
                    event = {
                        "type": kind,
                        "workflow": workflow,
                        "partId": part_id,
                        "turnId": self.turn_id,
                        "sequence": self.sequence + 1,
                        "messageId": str(self.assistant_id),
                        "inputMessageId": str(self.input_id),
                        "assistantMessageId": str(self.assistant_id),
                    }
                    # 个人工作流事件按片段身份去重, 避免重放时重复展示。
                    if not any(
                        item.get("type") == kind and item.get("partId") == part_id
                        for item in self.content["events"]
                    ):
                        self.content["events"].append(copy.deepcopy(event))
                    # A displayed registration result must survive a refresh even
                    # if the model's later turn fails or the subscriber disconnects.
                    # 注册结果立即保存, 不等待普通流式投影的节流间隔。
                    await self.save()
                    last_save = time.monotonic()
                # 兼容运行确认与交互请求事件, 所有事件都关联到本轮消息。
                elif kind in ("workflow_confirm", "interaction_required"):
                    event = {
                        **event,
                        "turnId": self.turn_id,
                        "inputMessageId": str(self.input_id),
                        "assistantMessageId": str(self.assistant_id),
                    }
                    self.content["events"].append(event)
                else:
                    continue
                # 先发送已识别事件, 再按时间间隔保存累计展示状态。
                await self.emit(event)
                if time.monotonic() - last_save >= 1:
                    await self.save()
                    last_save = time.monotonic()
            # 没有完整结束证据或发生错误都判为失败; 等待动作单独标记。
            if not completed or failed:
                self.content["delivery"] = "failed"
                self.content.setdefault("errorCode", "CHAT_INCOMPLETE")
            else:
                self.content["delivery"] = "waiting_action" if waiting else "completed"
            # 先保存终态投影, 再通知订阅者结束, 避免刷新后缺少最终回答。
            await self.save()
            await self.emit(
                {
                    "type": "done"
                    if self.content["delivery"] in {"completed", "waiting_action"}
                    else "error",
                    "code": self.content.get("errorCode"),
                    "finalModelMessageId": self.final_model_message_id,
                    "content": self._public_content(),
                }
            )
        # 异常或取消只标记结果未确认, 不能自动重新运行可能发生过的工具。
        except (Exception, asyncio.CancelledError):
            self.content["delivery"] = "unconfirmed"
            self.content["errorCode"] = "CHAT_UNCONFIRMED"
            try:
                await self.save()
            # 投影保存失败时保留原持久化运行状态, 不伪造成功。
            except Exception:
                pass  # Persisted RUNNING remains unconfirmed, never fake success.
            await self.emit({"type": "error", "code": "CHAT_UNCONFIRMED"})
        finally:
            try:
                # 无论正常、异常或取消都关闭原生迭代器, 释放执行会话资源。
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()
            finally:
                # 仍有订阅者时发送队列结束标记, 断连时不再等待队列消费。
                if not self.detached:
                    await self.pending.put(None)

    # 实时 SSE 消费与生产任务分离, 订阅结束只解除展示连接。
    async def stream(self) -> AsyncIterator[str]:
        try:
            while True:
                event = await self.pending.get()
                if event is None:
                    return
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        finally:
            self.detach()

    # 清空待发事件并标记断连, 使后台生产者可继续保存真实结果。
    def detach(self) -> None:
        self.detached = True
        # Also safe before the async generator starts (disconnect during headers).
        while not self.pending.empty():
            self.pending.get_nowait()


# 响应对象负责可靠解除订阅, 不承担业务执行的取消或重试。
class ChatStreamingResponse(StreamingResponse):
    def __init__(self, delivery: ChatDelivery) -> None:
        self.delivery = delivery
        super().__init__(
            delivery.stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    # 即便连接在响应头阶段退出, 也执行 detach 清理订阅状态。
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.delivery.detach()
