"""Synthetic execute_ability Tool boundary for the engine-first probe.

The types in this module are Runtime-owned experiment fixtures. They are not a
shared Capability contract and must not be promoted as release evidence.
"""

from collections.abc import Mapping, Sequence
import json
from typing import Annotated, Any, Callable, Literal

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from skillweave_contracts import TrustedInvocationContext, parse_identifier

from runtime_phase1.tool_admission import build_closed_tool_node


def _validate_ability_key(value: str) -> str:
    return parse_identifier(value, path="$.abilityKey")


AbilityKeyInput = Annotated[
    str,
    Field(strict=True, min_length=1, max_length=128),
    AfterValidator(_validate_ability_key),
]
AbilityExecutionPort = Callable[
    [str, Mapping[str, Any], TrustedInvocationContext],
    dict[str, Any],
]


class ExecuteAbilityModelArgs(BaseModel):
    """Closed model-visible arguments for the synthetic Ability probe."""

    model_config = ConfigDict(extra="forbid", strict=True)

    abilityKey: AbilityKeyInput
    arguments: dict[str, Any]


class ExecuteAbilityArgs(ExecuteAbilityModelArgs):
    """Add trusted ToolRuntime after original model-argument admission."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        arbitrary_types_allowed=True,
    )

    runtime: ToolRuntime[TrustedInvocationContext]


class SyntheticAbilityResult(BaseModel):
    """Strict engine-private result projected by the synthetic execution port."""

    model_config = ConfigDict(extra="forbid", strict=True)

    abilityKey: AbilityKeyInput
    environment: Literal["PRT", "ONLINE"]
    releaseRef: str = Field(strict=True, min_length=1)
    status: Literal["SUCCEEDED"]
    output: dict[str, Any]
    adapterCalled: Literal[True]
    runtimeRetryCount: Literal[0]
    synthetic: Literal[True]


def validate_execute_ability_model_args(
    value: object,
) -> ExecuteAbilityModelArgs:
    """Validate all original model arguments before ToolRuntime injection."""

    return ExecuteAbilityModelArgs.model_validate(value, strict=True)


def build_execute_ability_tool_node(tools: Sequence[BaseTool]) -> ToolNode:
    """Build a pre-injection-admitted ToolNode for execute_ability."""

    return build_closed_tool_node(
        tools,
        {"execute_ability": validate_execute_ability_model_args},
    )


def build_execute_ability_tool(port: AbilityExecutionPort) -> BaseTool:
    """Build the no-retry synthetic Ability Tool used only by the probe."""

    @tool(
        "execute_ability",
        args_schema=ExecuteAbilityArgs,
        response_format="content_and_artifact",
    )
    def execute_ability(
        abilityKey: str,
        arguments: dict[str, Any],
        runtime: ToolRuntime[TrustedInvocationContext],
    ) -> tuple[str, dict[str, Any]]:
        """Execute one engine-authorized synthetic Ability fixture."""

        request = ExecuteAbilityModelArgs.model_validate(
            {"abilityKey": abilityKey, "arguments": arguments},
            strict=True,
        )
        result = SyntheticAbilityResult.model_validate(
            port(request.abilityKey, request.arguments, runtime.context),
            strict=True,
        )
        if result.abilityKey != request.abilityKey:
            raise ValueError("resolved Ability does not match requested abilityKey")
        if result.environment != runtime.context.trusted_context.environment:
            raise ValueError(
                "resolved Ability environment does not match trusted context"
            )
        content = json.dumps(
            {"output": result.output, "status": result.status},
            ensure_ascii=False,
            sort_keys=True,
        )
        artifact = result.model_dump(exclude={"output", "status"})
        return content, artifact

    return execute_ability
