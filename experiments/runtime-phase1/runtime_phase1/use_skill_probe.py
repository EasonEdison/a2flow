"""Provisional use_skill adapter for the Phase 1 framework probe.

This module exists only to test public LangChain and LangGraph boundaries. It
does not own the shared Skill contract or production authorization policy.
"""

import json
from typing import Annotated, Any, Callable

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, WithJsonSchema
from skillweave_contracts import (
    TrustedInvocationContext,
    UseSkillRequest,
    UseSkillResult,
)


SKILL_KEY_PATTERN = r"^(?!.*[\r\n])[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*$"


def _validate_skill_key(value: str) -> str:
    """Apply the integrated neutral contract to model-selected keys."""

    return UseSkillRequest.from_mapping({"skillKey": value}).skill_key


SkillKeyInput = Annotated[
    str,
    Field(strict=True, min_length=1, max_length=128),
    AfterValidator(_validate_skill_key),
    WithJsonSchema(
        {
            "type": "string",
            "minLength": 1,
            "maxLength": 128,
            "pattern": SKILL_KEY_PATTERN,
        }
    ),
]
SkillResolver = Callable[[str, TrustedInvocationContext], dict[str, Any]]


class UseSkillArgs(BaseModel):
    """Validate model input and trusted ToolRuntime injection together."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        arbitrary_types_allowed=True,
    )

    skillKey: SkillKeyInput
    runtime: ToolRuntime[TrustedInvocationContext]


def build_use_skill_tool(resolver: SkillResolver) -> BaseTool:
    """Build a Tool that separates model content from trusted resolver evidence."""

    @tool(
        "use_skill",
        args_schema=UseSkillArgs,
        response_format="content_and_artifact",
    )
    def use_skill(
        skillKey: str,
        runtime: ToolRuntime[TrustedInvocationContext],
    ) -> tuple[str, dict[str, Any]]:
        """Load one authorized Skill by logical key."""

        request = UseSkillRequest.from_mapping({"skillKey": skillKey})
        resolved = UseSkillResult.from_mapping(
            resolver(request.skill_key, runtime.context)
        )
        if resolved.artifact.skill_key != request.skill_key:
            raise ValueError("resolved Skill does not match requested skillKey")
        if (
            resolved.artifact.environment
            != runtime.context.trusted_context.environment
        ):
            raise ValueError("resolved Skill environment does not match trusted context")

        content = json.dumps(
            resolved.content.to_mapping(),
            ensure_ascii=False,
            sort_keys=True,
        )
        server_artifact = {
            "contractRevision": resolved.contract_revision,
            "artifact": resolved.artifact.to_mapping(),
        }
        return content, server_artifact

    return use_skill
