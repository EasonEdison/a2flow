"""Engine-first Deep Agent assembly for bounded Phase 1 probes."""

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

from runtime_phase1.deep_agent_probe import IMPLICIT_DEEP_AGENT_TOOLS
from runtime_phase1.finalizer_probe import RequiredToolFinalizerAdmission
from runtime_phase1.tool_admission import (
    ClosedModelArgsAdmission,
    ModelArgsValidator,
)


def build_engine_spine_probe(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    validators: Mapping[str, ModelArgsValidator],
    required_tool_names: Sequence[str],
    *,
    harness_profile_key: str,
    checkpointer: Any = None,
    terminal_guard: Callable[[Any], None] | None = None,
) -> CompiledStateGraph:
    """Build the engine-first probe using only Runtime-owned Tools."""

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
    return create_deep_agent(
        model=model,
        checkpointer=checkpointer,
        tools=list(tools),
        system_prompt=(
            "Use authorized Skills and operations only through Runtime-owned Tools."
        ),
        middleware=[
            ClosedModelArgsAdmission(validators),
            RequiredToolFinalizerAdmission(required_tool_names, terminal_guard),
        ],
    )
