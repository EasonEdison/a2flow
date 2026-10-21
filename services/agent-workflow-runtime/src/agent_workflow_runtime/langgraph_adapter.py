"""Continuation through public LangGraph snapshot/Command APIs, without scheduling."""

from langgraph.types import Command

from .models import ActionRejected, Interaction


class LangGraphContinuation:
    """Bind the graph on the backend and select exactly one matching native interrupt."""

    def __init__(self, graph: object, *, lifecycle=None) -> None:
        self.graph = graph
        self.lifecycle = lifecycle

    def __call__(self, interaction: Interaction, control_request_id: str) -> object:
        # 恢复前核对运行活动状态，以及交互绑定的线程是否仍属于这个运行。
        if self.lifecycle is not None:
            scope = interaction.context.invocation_scope
            owner = interaction.context.trusted_context
            self.lifecycle.assert_active(owner, scope.run_id)
            run = self.lifecycle.read(owner, scope.run_id)
            # 交互记录保存线程归属，请求不能替换为别的检查点线程。
            if run.thread_id != interaction.graph_thread_id:
                raise ActionRejected("RUN_THREAD_MISMATCH")
        config = {"configurable": {"thread_id": interaction.graph_thread_id}}
        # 读取含子图的原生快照，后续必须精确定位一个匹配的中断。
        snapshot = self.graph.get_state(config, subgraphs=True)
        matches = {}

        def visit(state: object) -> None:
            # 递归遍历实际任务与中断，不根据节点名称猜测恢复位置。
            for task in state.tasks:
                for pending in task.interrupts:
                    value = pending.value
                    if not isinstance(value, dict):
                        continue
                    scope = interaction.context.invocation_scope
                    # 同时核对交互、运行、节点、应用及版本身份，防止恢复到相邻等待点。
                    if all(value.get(key) == expected for key, expected in {
                        "interactionId": interaction.interaction_id,
                        "runId": scope.run_id,
                        "nodeId": scope.node_id,
                        "applicationKey": interaction.application_key,
                        "versionId": interaction.application_version,
                    }.items()):
                        matches[pending.id] = pending
                # 原生等待可能发生在子图内部，因此继续检查嵌套任务状态。
                child = task.state
                if hasattr(child, "tasks"):
                    visit(child)

        visit(snapshot)
        # 零个或多个匹配都拒绝恢复，不能随意选一个中断继续。
        if len(matches) != 1:
            raise ActionRejected("NATIVE_INTERRUPT_MISMATCH")
        interrupt_id = next(iter(matches))
        # 恢复载荷只带保存的控制请求引用，业务成功必须由重放工具再查事实确认。
        command = Command(resume={interrupt_id: {"controlRequestId": control_request_id}})
        if self.lifecycle is not None:
            from .events import NODE_UNBLOCKED
            # 发布节点解阻事件后，经同一受控 Runner 继续图，沿用停止及完成门禁。
            self.lifecycle.publish_event(
                NODE_UNBLOCKED, run, payload={"nodeId": scope.node_id})
            from .native_control import ControlledRunRunner
            return ControlledRunRunner(self.lifecycle, None, None).invoke(run, self.graph, command)
        # 无生命周期的调用保留为独立实验适配路径，仍只使用 SDK 公开恢复 API。
        return self.graph.invoke(
            command,
            config,
            context=interaction.context,
        )
