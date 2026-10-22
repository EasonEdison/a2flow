"""Attended b-side composition: b-side app wired with the real chat runner.

Mirrors a2flow_bside.assembly but injects ChatLoopRunner (runtime chat engine)
instead of leaving the runner unwired. Composition-root code only.
"""

from __future__ import annotations

import importlib
import os
import re
from collections.abc import Callable, Mapping
from typing import Any

import psycopg
from a2flow_asset_store import BundleValidator, PostgresAssetRepository
from a2flow_bside.account_guard import AccountGuardConfig, PostgresAccountGuard
from a2flow_bside.app import create_app
from a2flow_bside.chat_runtime import ChatRuntime
from a2flow_bside.chat_wake import ChatWake
from a2flow_bside.config import BsideConfig
from a2flow_bside.notification_repository import (
    NotificationsRepository,
    notification_engine,
)
from a2flow_bside.persistence_types import DatabaseConnection
from a2flow_bside.repositories import (
    ConversationsRepository,
    MessagesRepository,
    RunOwnershipRepository,
    SchedulesRepository,
    SessionsRepository,
    UsersRepository,
)
from a2flow_bside.route_dependencies import CardActionPayload, MemoryState
from a2flow_bside.runtime_client import HttpRuntimeClient
from a2flow_bside.schedule_history import ScheduleHistoryRepository
from a2flow_bside.work_activities import WorkActivitiesRepository
from agent_workflow_runtime.application_runtime import PreparedApplication
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from fastapi import FastAPI
from langchain_core.messages import BaseMessage
from psycopg.rows import dict_row
from pydantic import SecretStr
from skillweave_contracts import TrustedContext

from .chat_runner import ChatLoopRunner

_FACTORY = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:"
    r"[A-Za-z_][A-Za-z0-9_]*"
)


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_BSIDE_CONFIGURATION:" + name)
    return value


def _load_validator(reference: str) -> BundleValidator:
    if not isinstance(reference, str) or not _FACTORY.fullmatch(reference):
        raise RuntimeError("INVALID_BSIDE_VALIDATOR_FACTORY")
    module_name, attribute = reference.split(":", 1)
    try:
        # Protected plugin factories must produce the concrete bundle validator.
        factory: Callable[[], BundleValidator] = getattr(
            importlib.import_module(module_name), attribute
        )
        validator = factory()
    except Exception:
        raise RuntimeError("BSIDE_VALIDATOR_UNAVAILABLE") from None
    if not callable(getattr(validator, "validate", None)):
        raise RuntimeError("BSIDE_VALIDATOR_UNAVAILABLE")
    return validator


def create_app_from_environment() -> FastAPI:
    config = BsideConfig.from_environment()
    validator = _load_validator(_required("A2FLOW_BSIDE_VALIDATOR_FACTORY"))
    repository = PostgresAssetRepository(
        config.conninfo,
        environment=config.environment,
        database=_required("A2FLOW_BSIDE_DATABASE_NAME"),
        validator=validator,
    )
    from agent_workflow_runtime.rpc_assets import RpcAssetReader
    from agent_workflow_runtime.rpc_client import RpcClient

    rpc = RpcClient.from_environment(os.environ)
    base_reader = RpcAssetReader(repository, config.namespace, rpc)

    def workflow_catalog(user_id: int) -> list[dict[str, Any]]:
        owner = TrustedContext.from_mapping({"userId": user_id, "environment": config.environment})
        return [dict(item) for item in reader.list_workflows(owner)]

    def _chat_model_configuration(
        reference: str,
        current_owner: TrustedContext,
    ) -> Mapping[str, object]:
        # The bside session layer already verified the owner; chat accepts any
        # trusted principal instead of the runtime host fixed identity.
        if reference != "deepseek-v4-flash":
            raise RuntimeError("MODEL_CONFIGURATION_NOT_FOUND")
        return {
            "model_id": "deepseek-v4-flash",
            "credential_ref": "env:DEEPSEEK_API_KEY",
            "timeout_seconds": 30.0,
            "options": {"thinking": "disabled", "max_tokens": 4096},
        }

    def _chat_model_secret(reference: str, current_owner: TrustedContext) -> SecretStr:
        if reference != "env:DEEPSEEK_API_KEY":
            raise RuntimeError("MODEL_CREDENTIAL_UNAVAILABLE")
        return SecretStr(os.environ["DEEPSEEK_API_KEY"])

    chat_model_factory = DeepSeekModelFactory(_chat_model_configuration, _chat_model_secret)

    def _chat_system_prompt(catalog_owner: TrustedContext) -> str:
        catalog_lines = []
        for item in reader.list_workflows(catalog_owner):
            catalog_lines.append("- 工作流 " + str(item.get("definitionKey")))
        for item in reader.list_skills(catalog_owner):
            catalog_lines.append("- 技能 " + str(item.get("skillKey")))
        return (
            "你是 A2Flow 数字员工助手。\n"
            "可用工作流与技能（调用时使用确切 key）：\n" + "\n".join(catalog_lines) + "\n"
            "当用户想执行工作流（例如活动策划、活动套餐）时，必须直接调用 "
            "propose_workflow_run 工具发起确认提案，不要只用文字描述；"
            "用户确认前绝不启动运行。用户要求创建或保存工作流时，使用个人工作流工具，"
            "创建成功只登记到本人的工作流目录，不调用 propose_workflow_run 或启动运行。"
            "其他任务可用 use_skill 调用技能。"
        )

    def _password_dsn() -> str:
        secret_path = os.environ.get("A2FLOW_BSIDE_POSTGRES_PASSWORD_FILE")
        if not secret_path:
            return config.conninfo
        with open(secret_path, "r", encoding="utf-8") as stream:
            password = stream.read().strip()
        return psycopg.conninfo.make_conninfo(config.conninfo, password=password)

    conninfo = _password_dsn()

    def connection_factory() -> DatabaseConnection:
        return psycopg.connect(
            conninfo,
            row_factory=dict_row,
            connect_timeout=5,
            options="-c statement_timeout=10000 -c lock_timeout=5000",
            application_name="a2flow-b-side-api",
        )

    from a2flow_asset_store.personal_workflows import (
        PersonalWorkflowReader,
        PersonalWorkflowRepository,
    )

    personal_workflows = PersonalWorkflowRepository(
        connection_factory,
        namespace=config.namespace,
        environment=config.environment,
        validator=validator,
    )
    reader = PersonalWorkflowReader(base_reader, personal_workflows)
    import json

    from agent_workflow_runtime.chat.persistence import ConversationStore
    from langchain_core.messages import AIMessage, HumanMessage

    message_repository = MessagesRepository(connection_factory)
    from a2flow_bside.errors import BsideError
    from agent_workflow_runtime.personal_memory import MemoryConflict, PersonalMemory

    personal_memory = PersonalMemory(conninfo)
    from a2flow_bside.durable_chat import DurableChat
    from agent_workflow_runtime.chat.cards import ChatCardStore
    from agent_workflow_runtime.chat.rpc_actions import RpcChatActionService
    from agent_workflow_runtime.chat.rpc_assets import RpcChatAssets
    from agent_workflow_runtime.models import ActionRejected

    def memory_owner(user_id: int) -> TrustedContext:
        return TrustedContext.from_mapping(
            {
                "userId": user_id,
                "environment": config.environment,
            }
        )

    def memory_view(user_id: int) -> MemoryState:
        return personal_memory.view(memory_owner(user_id))

    def memory_replace(user_id: int, settings: MemoryState) -> MemoryState:
        try:
            return personal_memory.replace(memory_owner(user_id), **settings)
        except MemoryConflict as exc:
            raise BsideError("MEMORY_REVISION_CONFLICT", 409) from exc
        except ValueError as exc:
            raise BsideError("INVALID_MEMORY_SETTINGS", 400) from exc

    def legacy_history(
        user_id: int,
        conversation_id: int,
        before_id: int,
    ) -> list[BaseMessage]:
        rows = message_repository.legacy_history(user_id, conversation_id, before_id)
        result: list[BaseMessage] = []
        for row in rows:
            content = row["content"]
            # Preserve legacy visible content, but never invent historical tool calls.
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            if isinstance(content, dict) and content.get("events"):
                text += "\nLegacy display events: " + json.dumps(
                    content["events"], ensure_ascii=False
                )
            cls = HumanMessage if row["role"] == "user" else AIMessage
            result.append(cls(content=text, id=f"legacy-{row['id']}"))
        return result

    work_activities = WorkActivitiesRepository(connection_factory)
    from a2flow_bside.processing_tasks import ProcessingTasksRepository

    processing_tasks = ProcessingTasksRepository(connection_factory, work_activities)

    # lifespan 提供已初始化的 wake；完成回调、请求服务和分发器共用同一仓库。
    def chat_runtime_factory(wake: ChatWake) -> ChatRuntime:
        durable_chat = DurableChat(connection_factory, environment=config.environment, wake=wake)
        card_store = ChatCardStore(
            conninfo,
            environment=config.environment,
            completion_observer=durable_chat.observe_completion,
        )

        def assets_factory(
            owner: TrustedContext,
            conversation_id: str,
            control_request_id: str = "chat-action",
            *,
            processing_context: Mapping[str, Any] | None = None,
            processing_turn_id: str | None = None,
        ) -> RpcChatAssets:
            def save_card(
                prepared: PreparedApplication,
                metadata: dict[str, Any],
            ) -> dict[str, Any]:
                return card_store.save(owner, conversation_id, prepared, metadata)

            return RpcChatAssets(
                reader=reader,
                rpc=rpc,
                processing_provider=processing_tasks,
                processing_context_value=processing_context,
                processing_turn_id=processing_turn_id,
                owner=owner,
                conversation_id=conversation_id,
                control_request_id=control_request_id,
                card_sink=save_card,
            )

        card_actions = RpcChatActionService(card_store, assets_factory)

        def chat_cards(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
            return card_store.list(memory_owner(user_id), conversation_id)

        def chat_action(
            user_id: int,
            conversation_id: str,
            card_id: str,
            payload: CardActionPayload,
        ) -> dict[str, Any]:
            try:
                return dict(
                    card_actions.execute(
                        memory_owner(user_id),
                        conversation_id,
                        card_id,
                        request_id=payload["requestId"],
                        action_name=payload["actionName"],
                        inputs=payload["inputs"],
                    )
                )
            except ActionRejected as exc:
                raise BsideError(exc.code, 409) from exc

        chat_runner = ChatLoopRunner(
            model_factory=chat_model_factory,
            model_reference="deepseek-v4-flash",
            environment=config.environment,
            reader=reader,
            system_prompt=_chat_system_prompt,
            conversation_store=ConversationStore(conninfo),
            history_loader=legacy_history,
            personal_memory=personal_memory,
            personal_workflows=reader,
            assets_factory=assets_factory,
            observation_loader=card_store.list_observations,
            workflow_run_provider=work_activities,
            processing_provider=processing_tasks,
        )

        return ChatRuntime(
            durable_chat=durable_chat,
            runner=chat_runner,
            cards=chat_cards,
            action=chat_action,
        )

    account_guard = PostgresAccountGuard(
        connection_factory,
        pepper=config.pepper,
        environment=config.environment,
        config=AccountGuardConfig.from_environment(os.environ),
    )
    account_guard.check_ready()

    return create_app(
        account_guard=account_guard,
        chat_runtime_factory=chat_runtime_factory,
        users=UsersRepository(connection_factory),
        sessions=SessionsRepository(connection_factory),
        conversations=ConversationsRepository(connection_factory),
        messages=message_repository,
        memory_view=memory_view,
        memory_replace=memory_replace,
        schedules=SchedulesRepository(connection_factory),
        notifications=NotificationsRepository(notification_engine(conninfo)),
        schedule_history=ScheduleHistoryRepository(notification_engine(conninfo)),
        run_ownership=RunOwnershipRepository(connection_factory),
        work_activities=work_activities,
        processing_tasks=processing_tasks,
        runtime_client=HttpRuntimeClient(config.runtime_url),
        workflow_catalog=workflow_catalog,
        pepper=config.pepper,
        browser_origin=config.browser_origin,
        browser_origins=config.browser_origins,
        environment=config.environment,
        session_seconds=config.session_seconds,
    )
