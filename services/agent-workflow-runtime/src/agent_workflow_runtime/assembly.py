"""Trusted Deep Agent assembly using public SDK hooks and injected Tools."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from .finalizer import RequiredToolFinalizerAdmission
from .tool_admission import (
    ClosedModelArgsAdmission,
    ModelArgsValidator,
)


IMPLICIT_DEEP_AGENT_TOOLS = frozenset({
    "delete", "edit_file", "execute", "glob", "grep", "ls",
    "read_file", "task", "write_file",
})


def build_engine(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    validators: Mapping[str, ModelArgsValidator],
    required_tool_names: Sequence[str],
    *,
    harness_profile_key: str,
    checkpointer: Any = None,
    terminal_guard: Callable[[Any], None] | None = None,
    run_lifecycle: Any = None,
    progress: Any = None,
    node_context: Any = None,
    system_prompt: str | None = None,
) -> CompiledStateGraph:
    """Build from trusted backend inputs, never request-selected Python internals.

    The service requires run_lifecycle and verifies RunGraphBinding. The optional
    unbound mode is retained only for standalone admission/Finalizer experiments.
    """

    if node_context is not None and run_lifecycle is None:
        raise ValueError("Node context requires run lifecycle")
    if system_prompt is not None and (not isinstance(system_prompt, str) or not system_prompt):
        raise ValueError("System prompt must be a nonempty string")
    if terminal_guard is None and any(
        (item.metadata or {}).get("requires_action_guard") for item in tools
    ):
        raise ValueError("Interactive Action Tools require a terminal guard")
    register_harness_profile(
        harness_profile_key,
        HarnessProfile(
            excluded_tools=IMPLICIT_DEEP_AGENT_TOOLS,
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )
    control_middleware = []
    if run_lifecycle is not None:
        from agent_workflow_runtime.native_control import (
            BoundNodeMiddleware, RunAdmissionMiddleware,
        )
        control_middleware = (
            [BoundNodeMiddleware(node_context)] if node_context is not None else []
        )
        control_middleware.append(RunAdmissionMiddleware(run_lifecycle, node_context))
    observation_middleware = []
    if progress is not None:
        from .progress_observer import ProgressMiddleware
        observation_middleware = [ProgressMiddleware(node_context)]
    graph = create_deep_agent(
        model=model,
        checkpointer=checkpointer,
        tools=list(tools),
        system_prompt=system_prompt or (
            "Use authorized Skills and operations only through Runtime-owned Tools."
        ),
        middleware=[
            *control_middleware,
            ClosedModelArgsAdmission(validators),
            *observation_middleware,
            RequiredToolFinalizerAdmission(
                required_tool_names, terminal_guard, lifecycle=run_lifecycle,
                node_context=node_context,
            ),
        ],
    )

    if run_lifecycle is not None:
        from agent_workflow_runtime.native_control import RunGraphBinding
        return RunGraphBinding(graph, run_lifecycle, progress)
    return graph
