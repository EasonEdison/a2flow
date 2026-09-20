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


def build_agent(
    model, tools, validators, *, harness_profile_key, middleware=(),
    checkpointer=None, context_schema=None, system_prompt=None,
    control_middleware=(),
):
    """Shared SDK construction; scope-specific lifecycle stays in middleware.

    No native Skill directory, filesystem execution or delegated agents are
    enabled here. Conversation mode does not require a tool for a greeting.
    """
    register_harness_profile(
        harness_profile_key,
        HarnessProfile(
            excluded_tools=IMPLICIT_DEEP_AGENT_TOOLS,
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )
    return create_deep_agent(
        model=model, tools=list(tools), checkpointer=checkpointer,
        context_schema=context_schema,
        system_prompt=system_prompt or (
            "Use authorized Skills and operations only through Runtime-owned Tools."
        ),
        middleware=[*control_middleware, ClosedModelArgsAdmission(validators),
                    *middleware],
    )


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
    personal_memory: Any = None,
) -> CompiledStateGraph:
    """Build from trusted backend inputs, never request-selected Python internals.

    The service requires run_lifecycle and verifies RunGraphBinding. The optional
    unbound mode is retained only for standalone admission/Finalizer experiments.
    """

    if node_context is not None and run_lifecycle is None:
        raise ValueError("Node context requires run lifecycle")
    if personal_memory is not None and node_context is None:
        raise ValueError("Personal memory requires a trusted node context")
    if system_prompt is not None and (not isinstance(system_prompt, str) or not system_prompt):
        raise ValueError("System prompt must be a nonempty string")
    if terminal_guard is None and any(
        (item.metadata or {}).get("requires_action_guard") for item in tools
    ):
        raise ValueError("Interactive Action Tools require a terminal guard")
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
    memory_middleware = []
    if personal_memory is not None:
        from .personal_memory import PersonalMemoryMiddleware
        memory_middleware = [PersonalMemoryMiddleware(
            personal_memory, node_context.trusted_context,
        )]
    if progress is not None:
        from .progress_observer import ProgressMiddleware
        observation_middleware = [ProgressMiddleware(node_context)]
    graph = build_agent(
        model=model,
        checkpointer=checkpointer,
        tools=list(tools),
        validators=validators,
        harness_profile_key=harness_profile_key,
        control_middleware=control_middleware,
        system_prompt=system_prompt or (
            "Use authorized Skills and operations only through Runtime-owned Tools."
        ),
        middleware=[
            *observation_middleware,
            *memory_middleware,
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
