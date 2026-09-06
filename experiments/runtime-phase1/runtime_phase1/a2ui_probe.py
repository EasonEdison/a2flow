"""Provisional render_application boundary for the Phase 1 probe."""

import hashlib
import json
from typing import Any, Callable

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field

from runtime_phase1.use_skill_probe import TrustedInvocationContext


ApplicationResolver = Callable[[str, TrustedInvocationContext], dict[str, Any]]


class RenderApplicationArgs(BaseModel):
    """Validate render input and trusted ToolRuntime injection together."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    applicationKey: str = Field(min_length=1)
    data: dict[str, Any]
    runtime: ToolRuntime[TrustedInvocationContext]


def build_render_application_tool(resolver: ApplicationResolver) -> BaseTool:
    """Build a render Tool with configuration-owned wait semantics."""

    @tool(
        "render_application",
        args_schema=RenderApplicationArgs,
        response_format="content_and_artifact",
    )
    def render_application(
        applicationKey: str,
        data: dict[str, Any],
        runtime: ToolRuntime[TrustedInvocationContext],
    ) -> tuple[str, dict[str, Any]]:
        """Render one authorized Application by logical key."""

        del data
        resolved = resolver(applicationKey, runtime.context)
        application = resolved["application"]
        interaction_mode = application["renderPolicy"]["interactionMode"]
        artifact = {
            "applicationKey": applicationKey,
            "contentDigest": resolved["contentDigest"],
            "interactionMode": interaction_mode,
            "resolvedVersion": resolved["resolvedVersion"],
        }

        if interaction_mode == "DISPLAY_ONLY":
            content = {
                "applicationKey": applicationKey,
                "interaction": None,
                "interactionMode": interaction_mode,
                "rendered": True,
            }
            return json.dumps(content, ensure_ascii=False, sort_keys=True), artifact

        if interaction_mode != "INTERACTIVE":
            raise ValueError(f"Unsupported interaction mode: {interaction_mode}")
        invocation_scope = runtime.context.invocation_scope
        if invocation_scope.kind != "WORKFLOW":
            raise ValueError("INTERACTIVE Application requires trusted Workflow scope")

        action_policy = application["actionPolicies"][0]
        version_id = resolved["resolvedVersion"]["versionId"]
        if not runtime.tool_call_id:
            raise ValueError("INTERACTIVE Application requires a Tool call identity")
        interaction_material = json.dumps(
            [
                invocation_scope.run_id,
                invocation_scope.node_id,
                runtime.context.control_request_id,
                applicationKey,
                version_id,
                runtime.tool_call_id,
            ],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        interaction_id = (
            "interaction:"
            f"{hashlib.sha256(interaction_material.encode('utf-8')).hexdigest()}"
        )
        interaction = {
            "actionName": action_policy["actionName"],
            "applicationKey": applicationKey,
            "interactionId": interaction_id,
            "kind": "A2UI_INTERACTION_REQUIRED",
            "nodeId": invocation_scope.node_id,
            "ordinaryChatMayResume": application["interactionPolicy"][
                "ordinaryChatMayResume"
            ],
            "runId": invocation_scope.run_id,
            "versionId": version_id,
        }
        interrupt(interaction)
        raise NotImplementedError(
            "Action validation and resume require PostgreSQL-backed verification"
        )

    return render_application
