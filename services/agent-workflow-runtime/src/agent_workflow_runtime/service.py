"""Transport-neutral service; host-supplied execution sessions own SDK resources."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

from skillweave_contracts import TrustedContext
from skillweave_contracts.models import parse_identifier
from skillweave_contracts.validation import ContractValidationError

from .actions import ActionService
from .lifecycle import RunLifecycle, RunRecord
from .models import ActionRejected, ActionRequest, json_copy
from .native_control import ControlledRunRunner

if TYPE_CHECKING:
    from .postgres_progress import PostgresProgress

# 入口必须接收认证层构造的 TrustedContext，普通字典不能冒充可信用户。

def require_owner(owner: object) -> TrustedContext:
    if type(owner) is not TrustedContext:
        raise ActionRejected("TRUSTED_CONTEXT_REQUIRED")
    return owner


# 资产或运行标识采用服务合同校验，控制请求 ID 则使用下面更严格的共享合同。
def identifier(value: object) -> str:
    if type(value) is not str or not value or len(value) > 256:
        raise ActionRejected("INVALID_SERVICE_INPUT")
    return value


def control_identifier(value: object) -> str:
    """Reuse the existing shared control ID contract, not generic asset/input rules."""
    # 复用共享请求 ID 规则，统一 HTTP 与直接服务调用的输入边界。
    try:
        return parse_identifier(value, path="$.controlRequestId")
    except ContractValidationError:
        raise ActionRejected("INVALID_SERVICE_INPUT") from None


# 展示读取只读已提交事实，不依赖可能被模型执行占用的会话锁。
class ProjectionPort(Protocol):
    """Independent committed reads; never enter an execution/admission scope."""

    def run(self, owner: TrustedContext, run_id: str) -> dict[str, Any]: ...
    def control(self, owner: TrustedContext, control_id: str) -> dict[str, Any]: ...
    def restart_identity(self, owner: TrustedContext, run_id: str) -> dict[str, Any]: ...


ActionServiceT = TypeVar("ActionServiceT", bound=ActionService, covariant=True)


@dataclass(frozen=True)
# 执行会话由宿主管理资源寿命，网络请求不得提供图、检查点或执行器。
class ExecutionSession(Generic[ActionServiceT]):
    """Trusted context manager yield value, never accepted from an HTTP request.

    The host owns checkpointer connections until the synchronous call ends.
    action_service(run) must bind the same lifecycle and controlled native graph.
    """

    runner: ControlledRunRunner
    action_service: Callable[[RunRecord], ActionServiceT]


class RuntimeService:
    def __init__(
        self,
        lifecycle: RunLifecycle,
        projection: ProjectionPort,
        execution_session: Callable[
            [TrustedContext], AbstractContextManager[ExecutionSession[ActionService]]
        ],
        resolve_entry: Callable[[TrustedContext, str], str],
        *,
        progress: PostgresProgress | None = None,
        validate_inputs: Callable[[TrustedContext, str, dict[str, Any]], None] | None = None,
    ) -> None:
        # 服务只组合可信端口，不在这一层增加模型循环或图调度。
        self.lifecycle = lifecycle
        self.projection = projection
        self.execution_session = execution_session
        self.resolve_entry = resolve_entry
        self.progress = progress
        self.validate_inputs = validate_inputs

    def _runner(self, session: ExecutionSession[ActionService]) -> ControlledRunRunner:
        # 宿主给出的 Runner 必须绑定当前生命周期，防止 Action 和 Stop 作用于不同状态源。
        runner = session.runner
        if not isinstance(runner, ControlledRunRunner) or runner.lifecycle is not self.lifecycle:
            raise ActionRejected("CONTROLLED_SERVICE_BINDING_REQUIRED")
        return runner

    # 运行与控制查询只读取投影，不触发资产解析、模型调用或恢复执行。
    def inspect(self, owner: TrustedContext, run_id: str) -> dict[str, Any]:
        return self.projection.run(require_owner(owner), identifier(run_id))

    def control(self, owner: TrustedContext, control_id: str) -> dict[str, Any]:
        # No execution session, definition resolver, graph, or control lock.
        return self.projection.control(require_owner(owner), control_identifier(control_id))

    def start(
        self,
        owner: TrustedContext,
        control_id: str,
        definition_key: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        require_owner(owner)
        control_identifier(control_id)
        identifier(definition_key)
        # 先复制并校验业务输入，再解析已发布定义的入口节点。
        if type(inputs) is not dict:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        copied_inputs = json_copy(inputs)
        assert isinstance(copied_inputs, dict)
        inputs = copied_inputs
        if self.validate_inputs is not None:
            self.validate_inputs(owner, definition_key, inputs)
        # 定义解析使用可信用户身份，模型或请求不能选择任意 Python 执行入口。
        entry = identifier(self.resolve_entry(owner, definition_key))
        # 资源作用域持续到同步受控执行结束，防止提前关闭检查点连接。
        with self.execution_session(owner) as session:
            response = self._runner(session).start(
                owner,
                control_id,
                definition_key,
                inputs,
                entry,
            )
        # Never serialize the runner's checkpoint/thread or business outcome.
        return self.inspect(owner, response["runId"])

    def stop(self, owner: TrustedContext, run_id: str, control_id: str) -> dict[str, Any]:
        require_owner(owner)
        identifier(run_id)
        control_identifier(control_id)
        # 停止直接进入生命周期短事务，避免等待繁忙的交互执行锁。
        response = self.lifecycle.stop(owner, run_id, control_id)
        # Stop does not depend on the potentially busy interaction projection.
        return {
            "runId": response["runId"],
            "lifecycle": response["status"],
            "delivery": "RETURNED",
        }

    def restart(
        self,
        owner: TrustedContext,
        run_id: str,
        control_id: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        require_owner(owner)
        identifier(run_id)
        control_identifier(control_id)
        if type(inputs) is not dict:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        copied_inputs = json_copy(inputs)
        assert isinstance(copied_inputs, dict)
        inputs = copied_inputs
        # A narrow identity read, not old inputs/results/version/checkpoint reuse.
        # 重启仅读取旧运行的定义身份，旧输入、结果和检查点都不用于新执行。
        old = self.projection.restart_identity(owner, run_id)
        definition = identifier(old["definitionKey"])
        # 新运行重新校验输入，并按当前生效定义解析入口。
        if self.validate_inputs is not None:
            self.validate_inputs(owner, definition, inputs)
        entry = identifier(self.resolve_entry(owner, definition))
        with self.execution_session(owner) as session:
            response = self._runner(session).start(
                # 通过旧运行 ID 验证重启来源，但创建的是新的 run 与 thread。
                owner,
                control_id,
                definition,
                inputs,
                entry,
                stopped_run_id=run_id,
            )
        return self.inspect(owner, response["runId"])

    def action(
        self, owner: TrustedContext, run_id: str, node_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        require_owner(owner)
        identifier(run_id)
        identifier(node_id)
        # 动作请求采用封闭字段集合，拒绝夹带运行身份、权限或额外恢复指令。
        if type(payload) is not dict or set(payload) != {
            "interactionId",
            "actionName",
            "controlRequestId",
            "inputs",
        }:
            raise ActionRejected("INVALID_SERVICE_INPUT")
        # 运行与节点由服务路由绑定，提交前按共享 Action 合同再次解析。
        bound = {**payload, "runId": run_id, "nodeId": node_id}
        control_identifier(bound["controlRequestId"])
        ActionRequest.from_mapping(bound)
        # 只有活动运行可受理新动作；实际执行仍会在更靠近调用处再次准入。
        run = self.lifecycle.read(owner, run_id)
        if run.status != "RUNNING":
            raise ActionRejected("RUN_STOPPED" if run.status == "STOPPED" else "RUN_NOT_ACTIVE")
        with self.execution_session(owner) as session:
            # 通过受控 Runner 校验完整恢复绑定后，再交由 ActionService 执行。
            runner = self._runner(session)
            runner.action(run, session.action_service(run), bound)
        return self.inspect(owner, run_id)

    # 进度读取有独立端口；未配置时明确报错，不伪造空的成功结果。
    def progress_catalog(
        self,
        owner: TrustedContext,
        run_id: str,
        *,
        after: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        require_owner(owner)
        if self.progress is None:
            raise ActionRejected("PROGRESS_UNAVAILABLE")
        return self.progress.catalog(owner, identifier(run_id), after=after, limit=limit)

    # 按可信运行和节点读取执行历史，分页参数交给进度端口按合同处理。
    def progress_history(
        self,
        owner: TrustedContext,
        run_id: str,
        node_id: str,
        execution_id: str,
        *,
        after: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        require_owner(owner)
        if self.progress is None:
            raise ActionRejected("PROGRESS_UNAVAILABLE")
        return self.progress.history(
            owner,
            identifier(run_id),
            identifier(node_id),
            execution_id,
            after=after,
            limit=limit,
        )
