"""Synchronous run control. Operation facts are an audit ledger, not a scheduler."""

from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
import json
from typing import Protocol
from uuid import uuid4

from skillweave_contracts import TrustedContext, TrustedInvocationContext
from .models import ActionRejected, json_copy
from .events import (
    DomainEvent, EventSink, NullSink, RUN_FAILED, RUN_FINISHED, RUN_STARTED, RUN_STOPPED,
    run_event_id,
)


# 停止使用独立控制信号，普通 Exception 重试不能把它捕获后再次执行业务。
class RunStoppedControl(BaseException):
    """Private control flow, deliberately outside ordinary business Exception retries."""

    def __init__(self, run_id):
        self.run_id = run_id
        super().__init__("RUN_STOPPED")


@dataclass(frozen=True)
# 运行记录保存业务生命周期及内部图线程；它与单次模型、工具操作账本分开。
class RunRecord:
    owner: TrustedContext
    run_id: str
    thread_id: str
    definition_key: str
    entry_node_id: str
    initial_inputs_json: str
    versions: tuple[tuple[str, str], ...]
    initial_control_id: str
    status: str = "RUNNING"
    revision: int = 0

    # 可信执行上下文由保存的运行记录构造，节点参数只能由受控装配指定。
    def context(self, node_id=None):
        return TrustedInvocationContext.from_mapping({
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
            "trustedContext": self.owner.to_mapping(),
            "invocationScope": {"kind": "WORKFLOW", "runId": self.run_id, "nodeId": self.entry_node_id if node_id is None else node_id},
            "controlRequestId": self.initial_control_id,
        })


@dataclass(frozen=True)
# 控制请求记录启动、停止或重启的幂等事实，不能等同于外部业务的恰好一次保证。
class RunControl:
    control_id: str
    payload_json: str
    run_id: str
    status: str = "DISPATCHING"


@dataclass(frozen=True)
# 每次准入记录操作身份、节点和状态修订，用于审计真实调用及其晚到结果。
class OperationFact:
    operation_id: str
    node_id: str
    kind: str
    admitted_revision: int
    status: str = "IN_FLIGHT"
    result_json: str | None = None


class RunLifecyclePort(Protocol):
    """All access occurs in a repository-owned short committed transaction.

    run_scope locks the run row; control_scope serializes one trusted control ID.
    No external model/tool/graph call can occur inside either scope. The PG adapter
    uses an independent connection, never an AF03 admission savepoint.
    """

    def run_scope(self, owner, run_id): ...
    def control_scope(self, owner, control_id): ...
    def get_run(self, owner, run_id, *, for_update=False): ...
    def restart_identity(self, owner, run_id): ...
    def put_run(self, run): ...
    def get_control(self, owner, control_id): ...
    def put_control(self, owner, control): ...
    def get_operation(self, owner, run_id, operation_id): ...
    def put_operation(self, owner, run_id, operation): ...
    def operations(self, owner, run_id): ...


# 规范化 JSON 用于请求内容比较，字段顺序变化不应破坏幂等判断。
def canonical(value):
    return json.dumps(json_copy(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def actual_json(value):
    """Explicit evidence encoding; no pickled or executable result representations."""
    from langchain_core.messages import BaseMessage, message_to_dict
    from langchain_core.outputs import LLMResult
    from langgraph.types import Command, Send
    # SDK 消息与模型结果显式转换为数据，不保存可执行对象或 pickle。
    if isinstance(value, BaseMessage):
        return actual_json(message_to_dict(value))
    if isinstance(value, LLMResult):
        return actual_json(value.model_dump(mode="json"))
    # 图控制结果也按固定数据结构保存，保留其实际跳转和更新语义。
    if isinstance(value, Command):
        return {"type": "Command", "update": actual_json(value.update),
                "goto": actual_json(value.goto), "graph": value.graph,
                "resume": actual_json(value.resume)}
    if isinstance(value, Send):
        return {"type": "Send", "node": value.node, "arg": actual_json(value.arg)}
    # 递归编码仅允许字符串键，最终由共享 JSON 校验拒绝不支持的值。
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            raise ActionRejected("INVALID_OPERATION_RESULT")
        return {key: actual_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [actual_json(item) for item in value]
    return json_copy(value)


class RunLifecycle:
    def __init__(self, repository: RunLifecyclePort, *, event_sink: EventSink | None = None,
                 waiting_validator=None):
        # 运行事实写入仓储，领域事件走注入端口；没有事件接收器时显式使用空实现。
        self.repository = repository
        self.event_sink = event_sink if event_sink is not None else NullSink()
        self.waiting_validator = waiting_validator
        # 进程内记录 SDK 可能掩盖的并行致命异常；这不是跨进程恢复队列。
        self._fatal_lock = Lock()
        self._fatals = {}

    def publish_event(self, event_type, run, *, payload=None):
        """Publish one trusted boundary event. A failing sink propagates;
        the RUN_FAILED call site alone keeps failures from masking its cause."""
        # 事件身份由可信运行记录构造，同类运行边界事件具有稳定去重 ID。
        self.event_sink.publish(DomainEvent.create(
            event_type, run.run_id, run.definition_key,
            run.owner.user_id, run.owner.environment, payload=payload,
            event_id=run_event_id(event_type, run.run_id, run.owner.user_id, run.owner.environment),
        ))

    def observe_fatal(self, owner, run_id, error):
        # 普通业务错误与正常停止不进入致命异常集合，避免被错误升级。
        if isinstance(error, RunStoppedControl) or isinstance(error, Exception):
            return
        with self._fatal_lock:
            self._fatals.setdefault((owner, run_id), []).append(error)

    def raise_observed_fatal(self, owner, run_id):
        # The synchronous native executor may suppress sibling fatal exceptions
        # when another task failed first. Each owned boundary records them here.
        # 受控入口重新抛出先前捕获的致命异常，不让其他并行失败将其吞掉。
        with self._fatal_lock:
            errors = self._fatals.get((owner, run_id), ())
        if errors:
            raise errors[0]

    @staticmethod
    # 未找到、已停止及其他终态分别处理，STOPPED 使用专用控制信号。
    def _active(run):
        if run is None:
            raise ActionRejected("RUN_NOT_FOUND")
        if run.status == "STOPPED":
            raise RunStoppedControl(run.run_id)
        if run.status != "RUNNING":
            raise ActionRejected("RUN_NOT_ACTIVE")

    # 读取和准入都受运行隔离范围约束，资源身份仍由仓储校验。
    def read(self, owner, run_id):
        with self.repository.run_scope(owner, run_id):
            run = self.repository.get_run(owner, run_id)
            if run is None:
                raise ActionRejected("RUN_NOT_FOUND")
            return run

    # 活动性检查使用短事务，不持锁等待模型或外部工具返回。
    def assert_active(self, owner, run_id):
        with self.repository.run_scope(owner, run_id):
            self._active(self.repository.get_run(owner, run_id))

    @contextmanager
    # 准入只预留一次调用并提交；实际模型、工具或网络执行必须在作用域之外发生。
    def admission(self, owner, run_id, node_id, kind, *, operation_id=None):
        """Reserve ONE actual invocation and commit before the caller dispatches.

        The caller may persist an AF03 EXECUTING record while this short run lock
        is held. That save commits on its independent admission connection. Scope
        exit then commits this fact. No savepoint is advertised as durable.
        """
        with self.repository.run_scope(owner, run_id):
            run = self.repository.get_run(owner, run_id)
            self._active(run)
            # 先写在途事实，后续完成记录才能明确关联这次准入。
            fact = OperationFact(operation_id or uuid4().hex, node_id, kind, run.revision)
            if self.repository.get_operation(owner, run_id, fact.operation_id) is not None:
                raise ActionRejected("OPERATION_ID_CONFLICT")
            self.repository.put_operation(owner, run_id, fact)
            yield fact

    def admit(self, owner, run_id, node_id, kind, *, operation_id=None):
        with self.admission(owner, run_id, node_id, kind, operation_id=operation_id) as fact:
            pass
        return fact

    # 节点边界恢复时可复用确定操作身份，但该方法本身不授权重试业务写入。
    def admit_idempotent(self, owner, run_id, node_id, kind, operation_id):
        """Reserve one deterministic graph boundary across checkpoint resumes."""
        with self.repository.run_scope(owner, run_id):
            run = self.repository.get_run(owner, run_id)
            self._active(run)
            # 同操作 ID 必须绑定相同节点和操作类型，冲突时不能复用其他执行记录。
            existing = self.repository.get_operation(owner, run_id, operation_id)
            if existing is not None:
                if existing.node_id != node_id or existing.kind != kind:
                    raise ActionRejected("OPERATION_ID_CONFLICT")
                return existing
            fact = OperationFact(operation_id, node_id, kind, run.revision)
            self.repository.put_operation(owner, run_id, fact)
            return fact

    def finish(self, owner, run_id, operation_id, result, *, status="RETURNED"):
        """Save actual outcome even after STOPPED; the first terminal fact is immutable."""
        from dataclasses import replace
        # 把实际返回值转为安全 JSON；保存结果不要求运行仍处于 RUNNING。
        document = canonical(actual_json(result))
        with self.repository.run_scope(owner, run_id):
            fact = self.repository.get_operation(owner, run_id, operation_id)
            if fact is None:
                raise ActionRejected("OPERATION_NOT_FOUND")
            # 第一个终态事实保持不变，例如停止检查产生的后续错误不能覆盖已保存响应。
            if fact.status != "IN_FLIGHT":
                # E.g. SDK emits on_llm_error after our post-result stop signal.
                return fact
            saved = replace(fact, status=status, result_json=document)
            self.repository.put_operation(owner, run_id, saved)
            return saved

    def execute(self, context, kind, handler):
        scope, owner = context.invocation_scope, context.trusted_context
        if scope.kind != "WORKFLOW":
            raise ActionRejected("WORKFLOW_BINDING_REQUIRED")
        # 先取得并提交准入，再执行处理器，确保停止与新调用有明确竞争边界。
        fact = self.admit(owner, scope.run_id, scope.node_id, kind)
        try:
            # 节点执行额外绑定进度观察；其他类型仍共用同一准入与结果保存流程。
            if kind == "NODE":
                from .progress_observer import observe_node
                with observe_node(context, fact.operation_id):
                    result = handler()
            else:
                result = handler()
        # 原生中断记录 INTERRUPTED，其余异常记录 UNCONFIRMED，均保留真实控制流。
        except BaseException as error:
            from langgraph.errors import GraphInterrupt
            self.observe_fatal(owner, scope.run_id, error)
            try:
                # 异常事实保存失败仅附加标记，不替换最初异常，也不自动补跑操作。
                self.finish(owner, scope.run_id, fact.operation_id, {"errorType": type(error).__name__},
                            status="INTERRUPTED" if isinstance(error, GraphInterrupt) else "UNCONFIRMED")
            except Exception:
                error.add_note("RUN_OPERATION_FACT_SAVE_UNCONFIRMED")
            raise
        # 先保存晚到成功，再检查是否允许继续，停止不会抹除已执行事实。
        self.finish(owner, scope.run_id, fact.operation_id, result)
        self.assert_active(owner, scope.run_id)
        return result

    def stop(self, owner, run_id, control_id):
        from dataclasses import replace
        # 停止请求以控制 ID 去重，相同 ID 改变目标运行会被拒绝。
        payload = canonical({"operation": "STOP", "runId": run_id})
        with self.repository.control_scope(owner, control_id):
            # 已有相同请求只返回保存的运行，不能再次调用图工厂。
            existing = self.repository.get_control(owner, control_id)
            if existing is not None:
                if existing.payload_json != payload:
                    raise ActionRejected("CONTROL_REQUEST_CONFLICT")
            else:
                # 停止锁定运行行，与每次新准入在同一状态边界串行竞争。
                run = self.repository.get_run(owner, run_id, for_update=True)
                if run is None:
                    raise ActionRejected("RUN_NOT_FOUND")
                if run.status not in {"RUNNING", "STOPPED"}:
                    raise ActionRejected("RUN_ALREADY_TERMINAL")
                # 提交 STOPPED 并递增修订后，新调用会被拒绝；在途调用仍可能返回结果。
                if run.status != "STOPPED":
                    self.repository.put_run(replace(run, status="STOPPED", revision=run.revision + 1))
                    self.publish_event(RUN_STOPPED, run)
                self.repository.put_control(owner, RunControl(control_id, payload, run_id, "RETURNED"))
        # The response never equates STOPPED to "all in-flight work has finished".
        return self.snapshot(owner, run_id)

    def snapshot(self, owner, run_id):
        with self.repository.run_scope(owner, run_id):
            run = self.repository.get_run(owner, run_id)
            if run is None:
                raise ActionRejected("RUN_NOT_FOUND")
            # 快照单独统计已准入未结束的外部调用，STOPPED 不表示所有网络调用都已结束。
            pending = tuple(f.operation_id for f in self.repository.operations(owner, run_id)
                            if f.status == "IN_FLIGHT" and f.kind in {"MODEL", "TOOL", "ACTION"})
            return {"runId": run_id, "threadId": run.thread_id, "status": run.status,
                    "inFlightCallsStillPending": bool(pending), "inFlightCallCount": len(pending)}

    # 仅关闭真正的运行失败，不改变此前成功业务操作或已有终态。
    def fail(self, owner, run_id: str, *, reason: str | None = None) -> RunRecord | None:
        """Close a real graph failure without changing successful business facts."""
        from dataclasses import replace
        with self.repository.run_scope(owner, run_id):
            run = self.repository.get_run(owner, run_id, for_update=True)
            if run is None:
                raise ActionRejected("RUN_NOT_FOUND")
            # 只有 RUNNING 可转为 FAILED，避免晚到异常覆盖停止或成功。
            if run.status != "RUNNING":
                return None
            failed = replace(run, status="FAILED", revision=run.revision + 1)
            self.repository.put_run(failed)
            self.publish_event(RUN_FAILED, failed, payload={"reason": reason} if reason else None)
        return failed

    # 成功同样经过运行活动性检查，防止停止之后迟到的图返回把运行改成成功。
    def succeed(self, owner, run_id):
        from dataclasses import replace
        with self.repository.run_scope(owner, run_id):
            run = self.repository.get_run(owner, run_id)
            self._active(run)
            self.repository.put_run(replace(run, status="SUCCEEDED", revision=run.revision + 1))
            self.publish_event(RUN_FINISHED, run)

    def allocate(self, owner, control_id, definition_key, inputs, entry_node_id, resolve_versions,
                 *, stopped_run_id=None):
        """Fresh stopped-run restart, not a rule freezing every future restart source."""
        # 启动及重启的完整输入进入幂等摘要；重启仍是新执行而非旧检查点恢复。
        payload = canonical({"operation": "RESTART_AFTER_STOP" if stopped_run_id else "START",
                             "stoppedRunId": stopped_run_id, "definitionKey": definition_key,
                             "inputs": inputs, "entryNodeId": entry_node_id})
        with self.repository.control_scope(owner, control_id):
            existing = self.repository.get_control(owner, control_id)
            if existing is not None:
                if existing.payload_json != payload:
                    raise ActionRejected("CONTROL_REQUEST_CONFLICT")
                return self.repository.get_run(owner, existing.run_id), False
            # 本实现只允许从 STOPPED 新建重启，并核对旧运行所属定义。
            if stopped_run_id is not None:
                old = self.repository.restart_identity(owner, stopped_run_id)
                if old is None:
                    raise ActionRejected("RUN_NOT_FOUND")
                if old["status"] != "STOPPED":
                    raise ActionRejected("RESTART_SOURCE_OUTSIDE_THIS_SLICE")
                if old["definitionKey"] != definition_key:
                    raise ActionRejected("RUN_DEFINITION_MISMATCH")
            # 新执行解析当前有效配置，不沿用旧运行历史输入或旧检查点。
            versions = tuple(resolve_versions(owner, definition_key))
            if not versions or len(dict(versions)) != len(versions):
                raise ActionRejected("INVALID_RUN_CONFIGURATION")
            # 分别生成新的运行 ID 和图线程 ID，同时保存请求回执与启动事件。
            run = RunRecord(owner, uuid4().hex, uuid4().hex, definition_key, entry_node_id,
                            canonical(inputs), versions, control_id)
            self.repository.put_run(run)
            self.repository.put_control(owner, RunControl(control_id, payload, run.run_id))
            self.publish_event(RUN_STARTED, run, payload={"entryNodeId": entry_node_id})
            return run, True

    # 控制投递状态单独更新，不能用图调用返回直接代替业务成功。
    def control_status(self, owner, control_id, status):
        from dataclasses import replace
        with self.repository.control_scope(owner, control_id):
            control = self.repository.get_control(owner, control_id)
            if control is None:
                raise ActionRejected("CONTROL_NOT_FOUND")
            self.repository.put_control(owner, replace(control, status=status))
