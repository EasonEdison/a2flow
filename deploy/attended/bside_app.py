"""Attended b-side composition: b-side app wired with the real chat runner.

Mirrors a2flow_bside.assembly but injects ChatLoopRunner (runtime chat engine)
instead of leaving the runner unwired. Composition-root code only.
"""

from __future__ import annotations

import importlib
import os
import re

import psycopg
from psycopg.rows import dict_row

from skillweave_contracts import TrustedContext

from a2flow_asset_store import AssetReader, PostgresAssetRepository
from a2flow_bside.app import create_app
from a2flow_bside.config import BsideConfig
from a2flow_bside.repositories import (
    ConversationsRepository,
    MessagesRepository,
    NotificationsRepository,
    RunOwnershipRepository,
    SchedulesRepository,
    SessionsRepository,
    UsersRepository,
)
from a2flow_bside.runtime_client import HttpRuntimeClient

from pydantic import SecretStr

from agent_workflow_runtime.model_factory import DeepSeekModelFactory

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


def _load_validator(reference: str):
    if not isinstance(reference, str) or not _FACTORY.fullmatch(reference):
        raise RuntimeError("INVALID_BSIDE_VALIDATOR_FACTORY")
    module_name, attribute = reference.split(":", 1)
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
        validator = factory()
    except Exception:
        raise RuntimeError("BSIDE_VALIDATOR_UNAVAILABLE") from None
    if not callable(getattr(validator, "validate", None)):
        raise RuntimeError("BSIDE_VALIDATOR_UNAVAILABLE")
    return validator


def create_app_from_environment():
    config = BsideConfig.from_environment()
    validator = _load_validator(_required("A2FLOW_BSIDE_VALIDATOR_FACTORY"))
    repository = PostgresAssetRepository(
        config.conninfo,
        environment=config.environment,
        database=_required("A2FLOW_BSIDE_DATABASE_NAME"),
        validator=validator,
    )
    reader = AssetReader(repository, config.namespace)

    def workflow_catalog(user_id: int):
        owner = TrustedContext.from_mapping({
            "userId": user_id, "environment": config.environment})
        return [dict(item) for item in reader.list_workflows(owner)]

    def _chat_model_configuration(reference, current_owner):
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

    def _chat_model_secret(reference, current_owner):
        if reference != "env:DEEPSEEK_API_KEY":
            raise RuntimeError("MODEL_CREDENTIAL_UNAVAILABLE")
        return SecretStr(os.environ["DEEPSEEK_API_KEY"])

    chat_model_factory = DeepSeekModelFactory(
        _chat_model_configuration, _chat_model_secret)

    def _chat_system_prompt(catalog_owner):
        catalog_lines = []
        for item in reader.list_workflows(catalog_owner):
            catalog_lines.append(
                "- 工作流 " + str(item.get("definitionKey")))
        for item in reader.list_skills(catalog_owner):
            catalog_lines.append(
                "- 技能 " + str(item.get("skillKey")))
        return (
            "你是 A2Flow 数字员工助手。\n"
            "可用工作流与技能（调用时使用确切 key）：\n"
            + "\n".join(catalog_lines) + "\n"
            "当用户想执行工作流（例如活动策划、活动套餐）时，必须直接调用 "
            "propose_workflow_run 工具发起确认提案，不要只用文字描述；"
            "用户确认前绝不启动运行。其他任务可用 use_skill 调用技能。"
        )

    def _password_dsn():
        secret_path = os.environ.get("A2FLOW_BSIDE_POSTGRES_PASSWORD_FILE")
        if not secret_path:
            return config.conninfo
        with open(secret_path, "r", encoding="utf-8") as stream:
            password = stream.read().strip()
        return psycopg.conninfo.make_conninfo(config.conninfo, password=password)

    conninfo = _password_dsn()
    connection_factory = lambda: psycopg.connect(
        conninfo, row_factory=dict_row, connect_timeout=5,
        options="-c statement_timeout=10000 -c lock_timeout=5000",
        application_name="a2flow-b-side-api",
    )
    from agent_workflow_runtime.chat.persistence import ConversationStore
    from langchain_core.messages import AIMessage, HumanMessage
    import json

    message_repository = MessagesRepository(connection_factory)
    from agent_workflow_runtime.personal_memory import PersonalMemory, MemoryConflict
    from a2flow_bside.errors import BsideError
    personal_memory = PersonalMemory(conninfo)

    def memory_owner(user_id):
        return TrustedContext.from_mapping({
            "userId": user_id, "environment": config.environment,
        })

    def memory_view(user_id):
        return personal_memory.view(memory_owner(user_id))

    def memory_replace(user_id, settings):
        try:
            return personal_memory.replace(memory_owner(user_id), **settings)
        except MemoryConflict as exc:
            raise BsideError("MEMORY_REVISION_CONFLICT", 409) from exc
        except ValueError as exc:
            raise BsideError("INVALID_MEMORY_SETTINGS", 400) from exc

    def legacy_history(user_id, conversation_id, before_id):
        rows = message_repository.legacy_history(user_id, conversation_id, before_id)
        result = []
        for row in rows:
            content = row["content"]
            # Preserve legacy visible content, but never invent historical tool calls.
            text = (content.get("text", "") if isinstance(content, dict)
                    else str(content))
            if isinstance(content, dict) and content.get("events"):
                text += "\nLegacy display events: " + json.dumps(
                    content["events"], ensure_ascii=False)
            cls = HumanMessage if row["role"] == "user" else AIMessage
            result.append(cls(content=text, id=f"legacy-{row['id']}"))
        return result

    chat_runner = ChatLoopRunner(
        model_factory=chat_model_factory, model_reference="deepseek-v4-flash",
        environment=config.environment, reader=reader,
        system_prompt=_chat_system_prompt,
        conversation_store=ConversationStore(conninfo),
        history_loader=legacy_history,
        personal_memory=personal_memory,
    )

    return create_app(
        users=UsersRepository(connection_factory),
        sessions=SessionsRepository(connection_factory),
        conversations=ConversationsRepository(connection_factory),
        messages=message_repository,
        memory_view=memory_view,
        memory_replace=memory_replace,
        schedules=SchedulesRepository(connection_factory),
        notifications=NotificationsRepository(connection_factory),
        run_ownership=RunOwnershipRepository(connection_factory),
        runtime_client=HttpRuntimeClient(config.runtime_url),
        chat_runner=chat_runner,
        workflow_catalog=workflow_catalog,
        pepper=config.pepper,
        browser_origin=config.browser_origin,
        environment=config.environment,
        session_seconds=config.session_seconds,
    )
