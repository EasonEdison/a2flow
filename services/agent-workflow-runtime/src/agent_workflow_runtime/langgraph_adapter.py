"""Continuation through public LangGraph snapshot/Command APIs, without scheduling."""

from langgraph.types import Command

from .models import ActionRejected, Interaction


class LangGraphContinuation:
    """Bind the graph on the backend and select exactly one matching native interrupt."""

    def __init__(self, graph: object) -> None:
        self.graph = graph

    def __call__(self, interaction: Interaction, control_request_id: str) -> object:
        config = {"configurable": {"thread_id": interaction.graph_thread_id}}
        snapshot = self.graph.get_state(config, subgraphs=True)
        matches = {}

        def visit(state: object) -> None:
            for task in state.tasks:
                for pending in task.interrupts:
                    value = pending.value
                    if not isinstance(value, dict):
                        continue
                    scope = interaction.context.invocation_scope
                    if all(value.get(key) == expected for key, expected in {
                        "interactionId": interaction.interaction_id,
                        "runId": scope.run_id,
                        "nodeId": scope.node_id,
                        "applicationKey": interaction.application_key,
                        "versionId": interaction.application_version,
                    }.items()):
                        matches[pending.id] = pending
                child = task.state
                if hasattr(child, "tasks"):
                    visit(child)

        visit(snapshot)
        if len(matches) != 1:
            raise ActionRejected("NATIVE_INTERRUPT_MISMATCH")
        interrupt_id = next(iter(matches))
        return self.graph.invoke(
            Command(resume={interrupt_id: {"controlRequestId": control_request_id}}),
            config,
            context=interaction.context,
        )
