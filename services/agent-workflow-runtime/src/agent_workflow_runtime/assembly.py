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
) -> CompiledStateGraph:
    """Build from trusted backend inputs, never request-selected Python internals.

    The service requires run_lifecycle and verifies RunGraphBinding. The optional
    unbound mode is retained only for standalone admission/Finalizer experiments.
    """

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
        from agent_workflow_runtime.native_control import RunAdmissionMiddleware
        control_middleware = [RunAdmissionMiddleware(run_lifecycle)]
    graph = create_deep_agent(
        model=model,
        checkpointer=checkpointer,
        tools=list(tools),
        system_prompt=(
            "Use authorized Skills and operations only through Runtime-owned Tools."
        ),
        middleware=[
            *control_middleware,
            ClosedModelArgsAdmission(validators),
            RequiredToolFinalizerAdmission(required_tool_names, terminal_guard, lifecycle=run_lifecycle),
        ],
    )

    if run_lifecycle is not None:
        from agent_workflow_runtime.native_control import RunGraphBinding
        return RunGraphBinding(graph, run_lifecycle)
    return graph
