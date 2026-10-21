"""Action admission, saved business outcomes and guarded interaction completion."""

from contextlib import nullcontext
from dataclasses import replace
import json

from skillweave_contracts import TrustedContext, TrustedInvocationContext

from .models import ActionRejected, ActionRequest, Attempt, Interaction, json_copy
from .policy import business_succeeded
from .ports import ConfigurationPort, ContinuationPort, ExecutorPort, InteractionRepository


class ActionService:
    """Own Action facts independently of models, transport status and graph replay."""

    def __init__(
        self, repository: InteractionRepository, configuration: ConfigurationPort,
        executor: ExecutorPort, continuation: ContinuationPort, *, lifecycle=None,
    ) -> None:
        # 交互事实、配置解析、业务执行和图恢复由独立端口承担，避免混成一个成功状态。
        self.repository = repository
        self.configuration = configuration
        self.executor = executor
        self.continuation = continuation
        self.lifecycle = lifecycle

    def register(self, interaction: Interaction) -> None:
        """Register one trusted card; replay never replaces history or bindings."""
        # 卡片必须绑定工作流运行和原生线程，不能注册成脱离任务的恢复入口。
        scope = interaction.context.invocation_scope
        if scope.kind != "WORKFLOW" or not interaction.graph_thread_id:
            raise ActionRejected("WORKFLOW_BINDING_REQUIRED")
        owner = interaction.context.trusted_context
        self._run_active(owner, scope.run_id)
        # 注册在所属运行的准入范围内串行进行，防止同卡片重复建立不同绑定。
        with self.repository.scope(owner, scope.run_id):
            existing = self.repository.get(interaction.key, owner)
            if existing is not None:
                # 比较不可变绑定时忽略运行态字段；重放只能复用原身份，不能覆盖已有历史。
                if replace(
                    existing, phase=interaction.phase, attempts=interaction.attempts,
                    run_active=interaction.run_active, node_waiting=interaction.node_waiting,
                    completion_request_id=interaction.completion_request_id,
                    resume_started=interaction.resume_started,
                    resume_consumed=interaction.resume_consumed,
                ) != interaction:
                    raise ActionRejected("INTERACTION_BINDING_CONFLICT")
                return
            self.repository.save(interaction)

    def _run_active(self, owner, run_id):
        if self.lifecycle is not None:
            self.lifecycle.assert_active(owner, run_id)

    def _active(self, interaction: Interaction, owner: TrustedContext) -> None:
        # 先检查运行，再检查卡片归属和等待状态，入口认证不能替代资源校验。
        self._run_active(owner, interaction.key[0])
        if interaction.context.trusted_context != owner:
            raise ActionRejected("NOT_AUTHORIZED")
        # 运行已停止或卡片不再等待时拒绝新动作，避免旧页面继续提交。
        if not interaction.run_active:
            raise ActionRejected("RUN_STOPPED")
        if not interaction.node_waiting or interaction.phase == "INVALIDATED":
            raise ActionRejected("INTERACTION_NOT_WAITING")

    def _get(self, key: tuple[str, str, str], owner: TrustedContext) -> Interaction:
        item = self.repository.get(key, owner)
        if item is None:
            raise ActionRejected("INTERACTION_NOT_FOUND")
        return item

    def submit(self, payload: object, owner: TrustedContext) -> Attempt:
        """Execute once per saved control request; failed/uncertain delivery never reexecutes."""
        # 提交先解析封闭动作合同；业务 RPC 卡片由其专用适配链路负责。
        request = ActionRequest.from_mapping(payload)
        if self.configuration is None or self.executor is None:
            raise ActionRejected("RPC_CARD_ACTION_REQUIRED")
        # 在运行准入锁下读取交互及旧请求事实，确保重复提交不会重复执行业务。
        with self.repository.scope(owner, request.run_id):
            interaction = self._get(request.key, owner)
            self._active(interaction, owner)
            # 同控制 ID 必须保持完全相同请求；旧执行中记录只返回未确认，不重新派发。
            for attempt in interaction.attempts:
                if attempt.request.control_request_id == request.control_request_id:
                    if attempt.request != request:
                        raise ActionRejected("CONTROL_REQUEST_CONFLICT")
                    return replace(attempt, status="EXECUTION_UNCONFIRMED") if attempt.status == "EXECUTING" else attempt
            # DISPATCHING may be healthy in-flight, not a confirmed failure.
            # Reject before writing any reservation for this new request.
            # 同运行存在未确认业务或恢复派发时，先阻断新操作，不能绕开未知结果。
            for item in self.repository.for_run(owner, request.run_id):
                if any(
                    a.status in {"EXECUTING", "EXECUTION_UNCONFIRMED"}
                    or a.resume_status in {"DISPATCHING", "UNCONFIRMED"}
                    for a in item.attempts
                ):
                    raise ActionRejected("RUN_OPERATION_PENDING_OR_UNCONFIRMED")
            # 只有等待中的交互可受理新动作，再按当前配置确认允许的动作名。
            if interaction.phase != "WAITING":
                raise ActionRejected("INTERACTION_NOT_WAITING")
            config = self.configuration.action(interaction, request.action_name)
            if config.action_name != request.action_name:
                raise ActionRejected("ACTION_NOT_ALLOWED")
            # 模型或用户输入必须通过配置合同，验证失败发生在业务调用之前。
            inputs = json.loads(request.inputs_json)
            if config.validate_input(inputs) is not True:
                raise ActionRejected("INVALID_ACTION_INPUT")
            pending = Attempt(request, "EXECUTING")
            # 动作还要取得运行生命周期准入，与停止在同一运行状态边界上竞争。
            gate = (
                self.lifecycle.admission(owner, request.run_id, request.node_id, "ACTION")
                if self.lifecycle is not None else nullcontext(None)
            )
            # 先保存 EXECUTING 预留记录；这一步与运行准入分别提交，均成功后才可派发。
            with gate as run_operation:
                # AF03 commits on its admission connection while the short run
                # transaction is open on ANOTHER connection, not a savepoint.
                self.repository.save(replace(
                    interaction, phase="EXECUTING", attempts=(*interaction.attempts, pending),
                ))
            # Both independent commits finish before external dispatch.
            # 提交完成后确认准入锁仍有效，再跨出数据库边界调用业务执行器。
            self.repository.check_scope()
            try:
                # 执行结果按 JSON 保存，并用配置策略判断业务成功，不能只看执行器是否返回。
                result = json_copy(self.executor(config, inputs, owner))
                success = business_succeeded(config, result)
                # 业务成功与是否完成交互是两个事实，成功的非完成动作仍保留等待。
                outcome = Attempt(
                    request, "EXECUTED", success,
                    success and config.completes_interaction,
                    json.dumps(result, allow_nan=False, sort_keys=True),
                )
            # 普通异常也可能发生在写入之后，保留未确认事实，不撤销预留或自动重跑。
            except Exception:
                # An exception may occur after a business side effect. Preserve the
                # reservation and never include arbitrary executor exception text.
                outcome = Attempt(request, "EXECUTION_UNCONFIRMED")
            # 致命异常仍向上传播；如已取得运行准入，尽力保存该操作的未知结果。
            except BaseException as error:
                if self.lifecycle is not None:
                    self.lifecycle.observe_fatal(owner, request.run_id, error)
                    # 事实保存失败只附加定位标记，不能用新异常掩盖最初的致命原因。
                    try:
                        self.lifecycle.finish(owner, request.run_id, run_operation.operation_id,
                                              {"errorType": type(error).__name__}, status="UNCONFIRMED")
                    except Exception:
                        error.add_note("RUN_OPERATION_FACT_SAVE_UNCONFIRMED")
                raise
            # 即使运行已停止也保存晚到业务结果；禁止推进与保留事实分别处理。
            if self.lifecycle is not None:
                self.lifecycle.finish(
                    owner, request.run_id, run_operation.operation_id,
                    json.loads(outcome.result_json) if outcome.result_json is not None else None,
                    status="RETURNED" if outcome.status == "EXECUTED" else "UNCONFIRMED",
                )
            # 重新读取当前交互再写结果，保留其间已发生的失效标记。
            latest = self._get(request.key, owner)
            self.repository.save(replace(
                latest,
                phase=("COMPLETED" if outcome.interaction_completed else "WAITING")
                if latest.phase != "INVALIDATED" else latest.phase,
                attempts=(*latest.attempts[:-1], outcome),
                # 只有符合完成策略的动作才登记恢复来源，普通成功动作不能恢复整段等待。
                completion_request_id=(
                    request.control_request_id if outcome.interaction_completed else None
                ),
            ))
            self._run_active(owner, request.run_id)
            # 尚未完成交互就直接返回业务回执，后续仍等待有效动作。
            if not outcome.interaction_completed:
                return outcome
            latest = self._get(request.key, owner)
            # Retain late business success even when progression is now prohibited.
            self._active(latest, owner)
            # 恢复调用前先落 DISPATCHING，出现断连后不能当作未派发再次恢复。
            self.repository.save(replace(
                latest, resume_started=True,
                attempts=tuple(
                    replace(attempt, resume_status="DISPATCHING")
                    if attempt.request.control_request_id == request.control_request_id
                    else attempt for attempt in latest.attempts
                ),
            ))
        # Native Tool execution may use another SDK worker thread. Never hold the
        # admission lock across graph invocation; the replayed Tool rechecks the
        # saved claim and active state before returning success.
        # 释放动作准入锁后再取得恢复锁，避免 SDK 重放工具跨线程回查时死锁。
        with self.repository.continuation_scope(owner, request.run_id):
            try:
                # 恢复前重查卡片和运行状态，刚才业务成功不代表此刻仍允许继续图。
                current = self._get(request.key, owner)
                self._active(current, owner)
                self.repository.check_scope()
                self._run_active(owner, request.run_id)
                # 仅传保存的请求引用给原生恢复器，重放工具自行核实真实完成事实。
                self.continuation(current, request.control_request_id)
                self.repository.check_scope()
                # 原生调用返回后仍检查停止，不能把停止中的返回误报成继续成功。
                if self.lifecycle is not None:
                    from .lifecycle import RunStoppedControl
                    if self.lifecycle.read(owner, request.run_id).status == "STOPPED":
                        raise RunStoppedControl(request.run_id)
            # 恢复拒绝或异常都保留未确认投递状态，不据此重新执行业务动作。
            except ActionRejected:
                self._delivery_status(request, "UNCONFIRMED", owner)
                raise
            except Exception:
                self._delivery_status(request, "UNCONFIRMED", owner)
                raise ActionRejected("RESUME_UNCONFIRMED") from None
            # RETURNED 只表示这次恢复调用返回，工作流其他分支仍可能等待。
            return self._delivery_status(request, "RETURNED", owner)

    def _delivery_status(self, request: ActionRequest, status: str, owner: TrustedContext) -> Attempt:
        """Persist delivery facts separately from business and completion policy."""
        self.repository.check_scope()
        # 恢复回执在自己的短保存范围中更新，不改变已记录的业务成功事实。
        with self.repository.scope(owner, request.run_id):
            item = self._get(request.key, owner)
            attempts = tuple(
                replace(attempt, resume_status=status)
                if attempt.request.control_request_id == request.control_request_id
                else attempt for attempt in item.attempts
            )
            self.repository.save(replace(item, attempts=attempts))
            return next(a for a in attempts if a.request == request)

    def completion(
        self, key: tuple[str, str, str], value: object,
        owner: TrustedContext,
    ) -> Attempt:
        """Resolve a resume reference against saved facts; ignore all claimed success."""
        # 重放只接受控制 ID 引用，不接受请求方声称的 success 或业务结果。
        if (
            not isinstance(value, dict)
            or set(value) != {"controlRequestId"}
            or not isinstance(value["controlRequestId"], str)
        ):
            raise ActionRejected("INVALID_RESUME_REFERENCE")
        # 在可信归属范围内回查保存的卡片完成事实，作为原生工具继续返回的依据。
        with self.repository.scope(owner, key[0]):
            item = self._get(key, owner)
            self._active(item, owner)

            # 完成状态、已开始恢复标记及控制 ID 必须共同匹配，避免伪造恢复载荷。
            if (
                item.phase != "COMPLETED" or not item.resume_started
                or item.completion_request_id != value["controlRequestId"]
            ):
                raise ActionRejected("INTERACTION_NOT_COMPLETED")
            # 仅消费实际业务成功且满足交互完成策略的那个动作回执。
            for attempt in item.attempts:
                if (
                    attempt.request.control_request_id == item.completion_request_id
                    and attempt.business_success and attempt.interaction_completed
                ):
                    self.repository.save(replace(item, resume_consumed=True))
                    return attempt
            raise ActionRejected("INTERACTION_NOT_COMPLETED")

    def assert_finalizable(self, context: TrustedInvocationContext) -> None:
        """Block terminal model output while any required interaction is unresolved."""
        # 最终回复门禁只作用于当前工作流节点，普通会话由其自身等待机制处理。
        scope = context.invocation_scope
        if scope.kind != "WORKFLOW":
            return
        self._run_active(context.trusted_context, scope.run_id)
        with self.repository.scope(context.trusted_context, scope.run_id):
            # 逐一核对本节点交互，任何未完成或未消费的必需卡片都会阻止最终答复。
            for item in self.repository.for_node(
                context.trusted_context, scope.run_id, scope.node_id,
            ):

                # 仍等待的卡片需重新验证活动状态；非等待记录也必须满足受控完成约束。
                if item.node_waiting:
                    self._active(item, context.trusted_context)
                elif (not item.run_active or item.phase != "COMPLETED"
                      or item.attempts or item.completion_request_id is not None
                      or item.resume_started or not item.resume_consumed):
                    raise ActionRejected("REQUIRED_INTERACTION_PENDING")
                if item.phase != "COMPLETED" or not item.resume_consumed:
                    raise ActionRejected("REQUIRED_INTERACTION_PENDING")
