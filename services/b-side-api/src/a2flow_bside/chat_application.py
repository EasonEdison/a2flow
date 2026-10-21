"""Chat admission and saved-card continuation application operations.

The product owns durable admission; the runtime still owns the agent loop.
"""

from __future__ import annotations

import asyncio

from .durable_chat import DurableChat
from .errors import BsideError
from .persistence_types import DatabaseConnection, MessageRecord
from .processing_tasks import ProcessingContext, ProcessingTasksRepository
from .repositories import MessagesRepository
from .route_dependencies import ChatAction, JsonObject
from .route_models import ChatCardAction, MessageSend
from .route_support import _bounded_run_reference
from .work_activities import WorkActivitiesRepository


# 产品服务管理消息准入和续聊登记, 模型工具循环仍归运行层。
class ChatApplicationService:
    def __init__(
        self,
        *,
        messages: MessagesRepository,
        environment: str,
        work_activities: WorkActivitiesRepository | None,
        processing_tasks: ProcessingTasksRepository | None,
        chat_action: ChatAction | None,
        durable_chat: DurableChat | None,
    ) -> None:
        # 依赖在装配时固定传入, 避免请求处理时动态查询全局服务。
        self.messages = messages
        self.environment = environment
        self.work_activities = work_activities
        self.processing_tasks = processing_tasks
        self.chat_action = chat_action
        self.durable_chat = durable_chat

    async def execute_chat_card_action(
        self, user_id: int, conversation_id: int, card_id: str, body: ChatCardAction
    ) -> JsonObject:
        # 动作服务未装配就明确拒绝, 不生成模拟提交结果。
        chat_action = self.chat_action
        if chat_action is None:
            raise BsideError("CHAT_APPLICATION_UNAVAILABLE", 503)
        # 先核对卡片与处理任务的绑定是否完整一致, 避免带着未确认的任务关系提交。
        if self.processing_tasks is not None:
            await asyncio.to_thread(
                self.processing_tasks.context_for_card,
                user_id=user_id,
                environment=self.environment,
                conversation_id=str(conversation_id),
                card_id=card_id,
            )
        # 真正动作在线程内执行, 提交参数保持固定协议与原请求号。
        response = await asyncio.to_thread(
            chat_action,
            user_id,
            str(conversation_id),
            card_id,
            {
                "requestId": body.requestId,
                "actionName": body.actionName,
                "inputs": body.inputs,
            },
        )
        # 只有动作服务返回可信续聊标记才进入恢复, 普通展示动作直接返回。
        marker = response.get("continuation")
        if marker is None:
            return response
        card = response.get("card", {})
        display = card.get("display", {})
        result = card.get("result", {})
        # This marker comes only from the trusted action service after it saved
        # the real write result. User inputs cannot opt into this continuation.
        # 临时交互必须保存 SUBMITTED 和结构化字段, 点击本身不是提交完成证据。
        submitted = (
            isinstance(result, dict)
            and result.get("status") == "SUBMITTED"
            and isinstance(result.get("values"), dict)
        )
        # 写审批必须具备服务端保存的结果, 不能拿用户输入冒充业务成功。
        write_completed = (
            isinstance(marker, dict) and marker.get("kind") == "WRITE_APPROVAL" and "result" in card
        )
        # 只允许已识别的临时协议或 Java 写确认协议触发续聊。
        temporary = (
            display.get("protocolProfile") == "a2flow.temporary.v1"
            and display.get("definitionSource") == "TEMPORARY"
        )
        confirmed_java = write_completed and display.get("protocolProfile") == "a2flow.java-rpc.v1"
        # 交叉检查卡片、会话、请求号和完成状态, 拒绝来源不一致的恢复。
        if (
            not isinstance(marker, dict)
            or marker.get("cardId") != card_id
            or not isinstance(marker.get("requestId"), str)
            or not marker["requestId"]
            or card.get("cardId") != card_id
            or card.get("conversationId") != str(conversation_id)
            or card.get("status") != "COMPLETED"
            or not (submitted or write_completed)
            or not (temporary or confirmed_java)
        ):
            raise BsideError("CHAT_CONTINUATION_UNCONFIRMED", 409)
        if self.durable_chat is None:
            raise BsideError("CHAT_DURABLE_DISPATCH_UNAVAILABLE", 503)
        # 先物化已经保存的续聊事实, 再以稳定引用领取对应消息。
        await asyncio.to_thread(self.durable_chat.materialize, self.messages, self.processing_tasks)
        _, input_message, assistant_message = await asyncio.to_thread(
            self.messages.claim_interaction_continuation,
            user_id=user_id,
            conversation_id=conversation_id,
            card_id=card_id,
            request_id=marker["requestId"],
            write_completed=write_completed,
        )
        # 把产品消息投影状态映射给前端; 未知状态保持 UNKNOWN。
        state = assistant_message["content"].get("delivery")
        statuses: dict[object, str] = {
            "queued": "RUNNING",
            "running": "RUNNING",
            "completed": "COMPLETED",
            "waiting_action": "COMPLETED",
            "unconfirmed": "NEEDS_REVIEW",
            "failed": "FAILED",
        }
        status = statuses.get(state, "UNKNOWN")
        # 返回消息 ID 供页面定位同一次续聊, 提交响应不再另起模型请求。
        return {
            **response,
            "continuation": {
                "cardId": card_id,
                "requestId": marker["requestId"],
                "status": status,
                "inputMessageId": str(input_message["id"]),
                "assistantMessageId": str(assistant_message["id"]),
            },
        }

    async def admit_message(self, body: MessageSend, user_id: int) -> JsonObject:
        conversation_id = body.conversationId
        durable_chat = self.durable_chat
        if durable_chat is None:
            raise BsideError("CHAT_DURABLE_DISPATCH_UNAVAILABLE", 503)

        # 先按客户端请求号查已接受轮次, 并核对完整请求负载是否相同。
        prior = await asyncio.to_thread(
            durable_chat.request,
            user_id=user_id,
            conversation_id=conversation_id,
            request_id=body.clientRequestId,
            payload=body.model_dump(),
        )

        # 重发直接复用原轮次, 不重复读取引用、创建处理任务或启动模型。
        if prior is not None:
            return prior

        processing_context = None

        processing_activity = None

        # 首次处理异常与继续已有任务都必须具备处理任务仓库。
        if body.processingTarget is not None or body.processingTaskId is not None:
            if self.processing_tasks is None:
                raise BsideError("PROCESSING_UNAVAILABLE", 503)
            # 已有任务按用户、环境和会话读取上下文, 禁止跨会话接管。
            if body.processingTaskId is not None:
                processing_context = await asyncio.to_thread(
                    self.processing_tasks.get_context,
                    user_id=user_id,
                    environment=self.environment,
                    conversation_id=str(conversation_id),
                    task_id=body.processingTaskId,
                )
                processing_activity = processing_context["activityId"]
            elif body.processingTarget is not None:
                processing_activity = body.processingTarget.activityId

        references = []

        seen = set()

        # 收集用户显式引用, 并将处理任务对应动态加入同一组真实结果。
        activity_ids = [r.activityId for r in body.runReferences]

        if processing_activity is not None and processing_activity not in activity_ids:
            activity_ids.append(processing_activity)

        # 限制引用数量, 避免把不受限的工作流输出塞入对话上下文。
        if len(activity_ids) > 3:
            raise BsideError("TOO_MANY_RUN_REFERENCES", 400)

        # 每个动态仅引用一次, 且必须经可信用户归属查询。
        for activity_id in activity_ids:
            if activity_id in seen:
                raise BsideError("DUPLICATE_RUN_REFERENCE", 400)
            seen.add(activity_id)
            if self.work_activities is None:
                raise BsideError("WORK_ACTIVITIES_UNAVAILABLE", 503)
            # 服务端读取已保存结果, 不能接受浏览器提供的业务结果正文。
            snapshot = await asyncio.to_thread(
                self.work_activities.get_result,
                user_id=user_id,
                environment=self.environment,
                activity_id=activity_id,
                limit=8000,
            )
            # 最终序列化大小再次限额, 保留截断信息和结果来源。
            references.append(_bounded_run_reference(snapshot))

        # 异常处理轮次需要与任务绑定同事务保存, 不能先发模型再补关系。
        if processing_activity is not None:
            processing_tasks = self.processing_tasks
            processing_request_id = body.processingRequestId
            # MessageSend validates this pairing before admission. Capture the
            # validated request and concrete repository for the transaction callback.
            assert processing_tasks is not None and processing_request_id is not None

            # 回调沿用任务仓库的事务连接, 同时建立轮次和客户端幂等映射。
            def observe_turn(
                connection: DatabaseConnection,
                context: ProcessingContext,
                input_message: MessageRecord,
                assistant_message: MessageRecord,
                *,
                new: bool,
            ) -> None:
                # 只有新处理轮次才插入待执行记录, 重发只关联已有消息。
                if new:
                    durable_chat.insert_turn(
                        connection,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        request_id="processing:" + processing_request_id,
                        digest=processing_request_id,
                        input_message=input_message,
                        assistant_message=assistant_message,
                        references=references,
                        processing_context=context,
                    )
                # 每个客户端请求号映射到同一对输入和助手消息。
                durable_chat.record_request(
                    connection,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    request_id=body.clientRequestId,
                    payload=body.model_dump(),
                    input_message=input_message,
                    assistant_message=assistant_message,
                )

            # 任务、消息及持久化轮次一起提交, 失败时不留下半套处理关系。
            (
                _created,
                processing_context,
                _input_message,
                _assistant_message,
            ) = await asyncio.to_thread(
                processing_tasks.begin_turn,
                user_id=user_id,
                environment=self.environment,
                conversation_id=str(conversation_id),
                request_id=processing_request_id,
                text=body.text,
                references=references,
                target=body.processingTarget.model_dump() if body.processingTarget else None,
                task_id=body.processingTaskId,
                turn_observer=observe_turn,
            )
            # 从已保存请求读取结果, 不凭回调局部变量推断准入成功。
            turn = await asyncio.to_thread(
                durable_chat.request,
                user_id=user_id,
                conversation_id=conversation_id,
                request_id=body.clientRequestId,
                payload=body.model_dump(),
            )
        # 普通对话通过同一持久化接收入口, 保留相同幂等和执行边界。
        else:
            turn = await asyncio.to_thread(
                durable_chat.receive,
                user_id=user_id,
                conversation_id=conversation_id,
                request_id=body.clientRequestId,
                payload=body.model_dump(),
                references=references,
            )

        # 完成准入必须得到轮次记录, 返回后由后台分发器负责执行。
        assert turn is not None
        return turn
