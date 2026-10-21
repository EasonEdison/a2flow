"""Workflow control operations with explicit runtime and ownership dependencies."""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import uuid

from fastapi import Request

from .errors import BsideError, RemoteRuntimeError
from .repositories import (
    RunOwnershipRepository,
)
from .route_dependencies import (
    JsonObject,
    WorkflowCatalog,
)
from .runtime_client import RuntimeClient

_LOGGER = logging.getLogger(__name__)


# 工作流应用服务管理归属和控制请求, 实际节点执行由 Runtime 负责。
class WorkflowApplicationService:
    def __init__(
        self,
        *,
        environment: str,
        run_ownership: RunOwnershipRepository,
        runtime_client: RuntimeClient,
        workflow_catalog: WorkflowCatalog,
    ) -> None:
        self.environment = environment
        self.run_ownership = run_ownership
        self.runtime_client = runtime_client
        self.workflow_catalog = workflow_catalog

    def require_run_owner(self, control_id: str, owner_user: int) -> None:
        # 未记录和他人运行统一返回不存在, 避免泄露跨账号资源。
        recorded = self.run_ownership.owner(control_id)
        if recorded is None:
            raise BsideError("NOT_FOUND", 404)
        if recorded != owner_user:
            raise BsideError("NOT_FOUND", 404)

    # 每次调用绑定可信用户与固定环境, 模型参数不能选择执行身份。
    def runtime(self, user_id: int) -> RuntimeClient:
        return self.runtime_client.for_user(user_id, self.environment)

    def resolve_run_id(self, control_id: str, user_id: int) -> str:
        # 控制请求号与真实运行号分开保存; 查询成功才建立二者关系。
        view = self.runtime(user_id).control(control_id)
        # 真实运行号可用后再绑定; SUBMITTED 仅表示已提交, 不代表执行完成。
        run_id = view.get("runId") or view.get("run_id")
        # 未返回真实运行号就保持未解析, 不能拿控制号代替运行事实。
        if not isinstance(run_id, str) or not run_id:
            raise BsideError("RUN_NOT_RESOLVED", 409)
        self.run_ownership.bind_run_id(control_id, run_id)
        return run_id

    def resolve_inputs(
        self, workflow_key: str, user_id: int, raw_input: JsonObject | str
    ) -> JsonObject:
        # Every start, including object inputs, must resolve the caller's catalog.
        # Scheduled runs carry a plain prompt; wrap it into the workflow's
        # single required string property when it has one.
        # 所有启动方式都要解析用户可见的有效目录, 包括直接传入对象的场景。
        entry = next(
            (
                item
                for item in self.workflow_catalog(user_id)
                if item.get("definitionKey") == workflow_key
            ),
            None,
        )
        # 目录不可见的工作流不能启动, 结构化输入也不能绕过资产可见性。
        if entry is None:
            raise BsideError("WORKFLOW_NOT_FOUND", 404)
        if not isinstance(raw_input, str):
            return raw_input
        # 文本仅可映射到唯一必填字符串字段, 其他结构不擅自猜测参数。
        schema = entry.get("inputSchema") or {}
        required = schema.get("required") or []
        properties = schema.get("properties") or {}
        if len(required) == 1 and properties.get(required[0], {}).get("type") == "string":
            return {required[0]: raw_input}
        raise BsideError("INVALID_INPUT", 400)

    async def start_for(
        self,
        user_id: int,
        workflow_key: str,
        raw_input: dict[str, object] | str,
        source_type: str = "manual",
    ) -> dict[str, str]:
        # 先分配控制身份并解析输入, 再保存产品侧归属预留。
        control_id = uuid.uuid4().hex
        inputs = await asyncio.to_thread(
            self.resolve_inputs,
            workflow_key,
            user_id,
            raw_input,
        )
        # 启动前记录归属, 使通信结果未知时用户仍能查到控制请求。
        await asyncio.to_thread(
            self.run_ownership.reserve,
            control_id=control_id,
            user_id=user_id,
            workflow_key=workflow_key,
            environment=self.environment,
            source_type=source_type,
        )
        runtime = self.runtime(user_id)
        # 只发送一次启动请求, 响应丢失不能证明执行层未接受。
        try:
            view = await asyncio.to_thread(runtime.start, control_id, workflow_key, inputs)
        except Exception as start_error:
            _LOGGER.warning(
                "Runtime start failed category=%s control_id=%s",
                type(start_error).__name__,
                control_id,
            )
            # 只有连接不可达进入同一控制请求的事实查询, 其他错误原样传播。
            if (
                not isinstance(start_error, RemoteRuntimeError)
                or start_error.code != "RUNTIME_UNREACHABLE"
            ):
                raise
            # A failed HTTP response does not prove failed admission. Read the
            # same durable control once; never submit the business start again.
            try:
                # 恢复只查询原控制号, 不重新提交可能产生业务副作用的启动。
                view = await asyncio.to_thread(runtime.control, control_id)
                if (
                    # 核对控制号和真实运行号, 防止把不完整响应当成成功准入。
                    view.get("controlRequestId") != control_id
                    or not isinstance(view.get("runId"), str)
                    or not view["runId"]
                ):
                    raise ValueError("INVALID_CONTROL_ADMISSION")
            # 仍查不到可靠事实时保留归属并报原错误, 不宣称成功。
            except Exception as query_error:
                _LOGGER.warning(
                    "Runtime start unresolved category=%s control_id=%s",
                    type(query_error).__name__,
                    control_id,
                )
                # Keep ownership visible in My Runs, but do not claim success.
                raise start_error from None
        run_id = view.get("runId")
        if isinstance(run_id, str) and run_id:
            await asyncio.to_thread(self.run_ownership.bind_run_id, control_id, run_id)
        return {"controlRequestId": control_id, "status": "SUBMITTED"}

    # 内部接口需要受保护配置中的令牌, 未配置时整条入口关闭。
    def require_internal(self, request: Request) -> None:
        token = os.environ.get("A2FLOW_BSIDE_INTERNAL_TOKEN")
        if not token:
            raise BsideError("INTERNAL_API_DISABLED", 503)
        # 恒定时间比较内部令牌, 不信任浏览器会话替代内部凭据。
        provided = request.headers.get("x-a2flow-internal-token") or ""
        if not hmac.compare_digest(provided, token):
            raise BsideError("INTERNAL_TOKEN_REQUIRED", 401)

    def progress_query(self, request: Request, *, streaming: bool = False) -> list[tuple[str, str]]:
        # 保留所有游标参数交给原生校验, 避免中间层吞掉重复字段。
        query = request.query_params.multi_items()
        # Last-Event-ID 只用于流式读取, 不能与 after 同时指定。
        if request.headers.get("last-event-id") is not None and (
            not streaming or "after" in request.query_params
        ):
            raise BsideError("INVALID_PROGRESS_CURSOR", 400)
        # Keep all pairs, including duplicate or unknown keys, for native validation.
        return query
