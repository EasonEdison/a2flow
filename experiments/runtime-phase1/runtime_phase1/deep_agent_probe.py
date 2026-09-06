"""Provisional Deep Agents construction boundary for the Phase 1 probe."""

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph


IMPLICIT_DEEP_AGENT_TOOLS = frozenset(
    {
        "delete",
        "edit_file",
        "execute",
        "glob",
        "grep",
        "ls",
        "read_file",
        "task",
        "write_file",
    }
)


def build_deep_agent_probe(
    model: BaseChatModel,
    use_skill_tool: BaseTool,
    *,
    harness_profile_key: str,
) -> CompiledStateGraph:
    """Build a Deep Agent whose model sees only Runtime-owned tools."""

    register_harness_profile(
        harness_profile_key,
        HarnessProfile(
            excluded_tools=IMPLICIT_DEEP_AGENT_TOOLS,
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )

    return create_deep_agent(
        model=model,
        tools=[use_skill_tool],
        system_prompt="Use authorized Skills only through the use_skill Tool.",
    )
