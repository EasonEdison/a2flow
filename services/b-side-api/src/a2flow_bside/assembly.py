"""Composition root for the b-side service (environment factory).

Mirrors the management preview host's fail-closed style: every value is an
explicit protected configuration; import performs no connection or listener
work. The workflow catalog reads the current environment's published
WORKFLOW assets through the reviewed AssetReader.
"""

from __future__ import annotations

import importlib
import os
import re
from collections.abc import Callable
from typing import Any

import psycopg
from a2flow_asset_store import AssetReader, BundleValidator, PostgresAssetRepository
from fastapi import FastAPI
from psycopg.rows import dict_row
from skillweave_contracts import TrustedContext

from .account_guard import AccountGuardConfig, PostgresAccountGuard
from .app import create_app
from .config import BsideConfig
from .notification_repository import NotificationsRepository, notification_engine
from .persistence_types import DatabaseConnection
from .repositories import (
    ConversationsRepository,
    MessagesRepository,
    RunOwnershipRepository,
    SchedulesRepository,
    SessionsRepository,
    UsersRepository,
)
from .runtime_client import HttpRuntimeClient
from .schedule_history import ScheduleHistoryRepository

# 插件工厂引用限定为模块与属性名, 避免把配置当作可执行表达式。
_FACTORY = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:"
    r"[A-Za-z_][A-Za-z0-9_]*"
)


def _load_validator(reference: str) -> BundleValidator:
    # 先验证工厂定位格式, 再进行受保护配置指定的导入。
    if not isinstance(reference, str) or not _FACTORY.fullmatch(reference):
        raise RuntimeError("INVALID_BSIDE_VALIDATOR_FACTORY")
    module_name, attribute = reference.split(":", 1)
    try:
        # Protected plugin factories must produce the concrete bundle validator.
        factory: Callable[[], BundleValidator] = getattr(
            importlib.import_module(module_name), attribute
        )
        # 工厂必须产出具有 validate 接口的验证器, 否则关闭资产装配。
        validator = factory()
    except Exception:
        raise RuntimeError("BSIDE_VALIDATOR_UNAVAILABLE") from None
    if not callable(getattr(validator, "validate", None)):
        raise RuntimeError("BSIDE_VALIDATOR_UNAVAILABLE")
    return validator


def create_app_from_environment() -> FastAPI:
    """Uvicorn factory; every value is explicit protected configuration."""
    # 启动阶段一次性构造配置和资产读取器, 导入模块本身不连接数据库。
    config = BsideConfig.from_environment()
    validator = _load_validator(_required("A2FLOW_BSIDE_VALIDATOR_FACTORY"))
    repository = PostgresAssetRepository(
        config.conninfo,
        environment=config.environment,
        database=_required("A2FLOW_BSIDE_DATABASE_NAME"),
        validator=validator,
    )
    # 基础读取器读取当前环境的有效发布; 个人工作流随后叠加用户隔离。
    base_reader = AssetReader(repository, config.namespace)

    # 目录查询绑定服务端用户和环境, 调用者不能指定其他身份或泳道。
    def workflow_catalog(user_id: int) -> list[dict[str, Any]]:
        owner = TrustedContext.from_mapping({"userId": user_id, "environment": config.environment})
        return [dict(item) for item in reader.list_workflows(owner)]

    # 每次操作获取字典行连接, 并设置连接、语句和锁等待上限。
    def connection_factory() -> DatabaseConnection:
        return psycopg.connect(
            config.conninfo,
            row_factory=dict_row,
            connect_timeout=5,
            options="-c statement_timeout=10000 -c lock_timeout=5000",
            application_name="a2flow-b-side-api",
        )

    from a2flow_asset_store.personal_workflows import (
        PersonalWorkflowReader,
        PersonalWorkflowRepository,
    )

    # 组合预制与个人工作流读取器, 共用验证器和环境边界。
    reader = PersonalWorkflowReader(
        base_reader,
        PersonalWorkflowRepository(
            connection_factory,
            namespace=config.namespace,
            environment=config.environment,
            validator=validator,
        ),
    )

    # 账号防护预算使用同一数据库, 并在服务启动前检查可用性。
    account_guard = PostgresAccountGuard(
        connection_factory,
        pepper=config.pepper,
        environment=config.environment,
        config=AccountGuardConfig.from_environment(os.environ),
    )
    account_guard.check_ready()

    # 手动装配 HTTP 服务; 会话、消息、计划和运行归属由各自仓库负责。
    return create_app(
        account_guard=account_guard,
        users=UsersRepository(connection_factory),
        sessions=SessionsRepository(connection_factory),
        conversations=ConversationsRepository(connection_factory),
        messages=MessagesRepository(connection_factory),
        schedules=SchedulesRepository(connection_factory),
        notifications=NotificationsRepository(notification_engine(config.conninfo)),
        schedule_history=ScheduleHistoryRepository(notification_engine(config.conninfo)),
        run_ownership=RunOwnershipRepository(connection_factory),
        # 执行通过运行服务客户端发起, 产品 API 不自己维护 Agent 循环。
        runtime_client=HttpRuntimeClient(config.runtime_url),
        workflow_catalog=workflow_catalog,
        pepper=config.pepper,
        browser_origin=config.browser_origin,
        browser_origins=config.browser_origins,
        environment=config.environment,
        session_seconds=config.session_seconds,
    )


def _required(name: str) -> str:
    import os

    # 部署必需的配置缺失直接报错, 不猜测插件或资产数据库。
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_BSIDE_CONFIGURATION:" + name)
    return value
