"""Engine-first Deep Agent assembly for bounded Phase 1 probes."""

from collections.abc import Mapping, Sequence

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
) -> CompiledStateGraph:
    """Build the engine-first probe using only Runtime-owned Tools."""

    register_harness_profile(
        harness_profile_key,
        HarnessProfile(
            excluded_tools=IMPLICIT_DEEP_AGENT_TOOLS,
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )
    return create_deep_agent(
        model=model,
        tools=list(tools),
        system_prompt=(
            "Use authorized Skills and operations only through Runtime-owned Tools."
        ),
        middleware=[
            ClosedModelArgsAdmission(validators),
            RequiredToolFinalizerAdmission(required_tool_names),
        ],
    )
