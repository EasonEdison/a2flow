"""Provisional render_application boundary for the Phase 1 probe."""

from collections.abc import Sequence
import hashlib
import json
from typing import Any, Callable

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field

from runtime_phase1.tool_admission import build_closed_tool_node
from runtime_phase1.use_skill_probe import TrustedInvocationContext


ApplicationResolver = Callable[[str, TrustedInvocationContext], dict[str, Any]]


class RenderApplicationModelArgs(BaseModel):
    """Closed model-visible arguments for render_application."""

    model_config = ConfigDict(extra="forbid", strict=True)

    applicationKey: str = Field(strict=True, min_length=1)
    data: dict[str, Any]


class RenderApplicationArgs(RenderApplicationModelArgs):
    """Add trusted ToolRuntime after original model-argument admission."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        arbitrary_types_allowed=True,
    )

    runtime: ToolRuntime[TrustedInvocationContext]


def validate_render_application_model_args(
    value: object,
) -> RenderApplicationModelArgs:
    """Validate the complete original render request before injection."""

    return RenderApplicationModelArgs.model_validate(value, strict=True)


def build_render_application_tool_node(tools: Sequence[BaseTool]) -> ToolNode:
    """Build a pre-injection-admitted ToolNode for render_application."""

    return build_closed_tool_node(
        tools,
        {"render_application": validate_render_application_model_args},
    )


def build_render_application_tool(
    resolver: ApplicationResolver, *, action_service: Any = None,
) -> BaseTool:
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
        if action_service is None:
            interrupt(interaction)
            raise RuntimeError("Action service is required for interactive resume")

        from agent_workflow_runtime import ActionRejected, Interaction

        saved = Interaction(
            context=runtime.context,
            interaction_id=interaction_id,
            application_key=applicationKey,
            application_version=version_id,
            graph_thread_id=runtime.config["configurable"]["thread_id"],
            recorded_versions=tuple(resolved["recordedVersions"]),
        )
        action_service.register(saved)
        while True:
            reference = interrupt(interaction)
            try:
                outcome = action_service.completion(
                    saved.key, reference, runtime.context.trusted_context,
                )
                break
            except ActionRejected as error:
                if error.code not in {"INVALID_RESUME_REFERENCE", "INTERACTION_NOT_COMPLETED"}:
                    raise
                # An unsupported direct Command cannot turn unverified input into
                # Tool success. Keep the native wait and prevent successors.
                continue
        content = {
            "applicationKey": applicationKey,
            "interactionMode": interaction_mode,
            "rendered": True,
            "businessSuccess": outcome.business_success,
            "interactionCompleted": outcome.interaction_completed,
            "result": json.loads(outcome.result_json),
        }
        artifact["interactionId"] = interaction_id
        return json.dumps(content, ensure_ascii=False, sort_keys=True), artifact

    render_application.metadata = {"requires_action_guard": action_service is not None}
    return render_application
