"""RPC-backed Workflow assembly; generic Skill execution stays in Deep Agents."""

from __future__ import annotations

import json
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any

from fastapi import Request
from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict, Field
from skillweave_contracts import TrustedInvocationContext

from .assembly import build_engine
from .chat.cards import ChatCardStore, CompletionObserver, JsonObject
from .chat.tools import (
    AbilityArgs,
    QuerySkillDependenciesArgs,
    QuerySkillDependenciesModelArgs,
    RenderArgs,
    RenderModelArgs,
    UseSkillArgs,
    UseSkillModelArgs,
)
from .http import _Lane
from .langgraph_adapter import LangGraphContinuation
from .models import ActionRejected
from .mvp_assembly import MvpRuntimeHost, _close_model, validate_workflow_inputs
from .mvp_host import create_mvp_app
from .mvp_tools import AbilityModelArgs
from .native_control import ControlledRunRunner
from .rpc_assets import RpcAssetReader
from .rpc_client import RpcClient
from .service import ExecutionSession
from .workflow_loader import compose_workflow
from .workflow_rpc import WorkflowActions, WorkflowAssets


class CardActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requestId: str = Field(min_length=1, max_length=128)
    nodeId: str = Field(min_length=1, max_length=128)
    interactionId: str = Field(min_length=1, max_length=128)
    actionName: str = Field(min_length=1, max_length=128)
    inputs: dict[str, Any]


class CardResumeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requestId: str = Field(min_length=1, max_length=128)
    nodeId: str = Field(min_length=1, max_length=128)
    interactionId: str = Field(min_length=1, max_length=128)


def tools_for(assets: WorkflowAssets, actions: WorkflowActions) -> tuple[BaseTool, ...]:
    @tool("use_skill", args_schema=UseSkillArgs, response_format="content_and_artifact")
    def use_skill(skillKey: str, runtime: ToolRuntime[TrustedInvocationContext]) -> tuple[str, Any]:
        """Load the current node's authorized Skill instructions."""
        assets.validate_context(runtime.context)
        value = assets.admit_skill(skillKey)
        return json.dumps(value["content"], ensure_ascii=False), value["artifact"]

    @tool("execute_ability", args_schema=AbilityArgs, response_format="content_and_artifact")
    def execute_ability(
        abilityKey: str, arguments: dict[str, Any], runtime: ToolRuntime[TrustedInvocationContext]
    ) -> tuple[str, Any]:
        """Run an Ability bound by the current node Skill."""
        assets.validate_context(runtime.context)
        assets.current()
        value = assets.execute_ability(abilityKey, arguments)
        return json.dumps(value["output"], ensure_ascii=False), {
            "abilityKey": abilityKey,
            "versionId": value["versionId"],
        }

    @tool("query_skill_dependencies", args_schema=QuerySkillDependenciesArgs)
    def query_skill_dependencies(
        a2uiApplicationCodeList: list[str], runtime: ToolRuntime[TrustedInvocationContext]
    ) -> str:
        """Read published Application params contracts before rendering."""
        assets.validate_context(runtime.context)
        assets.current()
        return json.dumps(
            assets.query_skill_dependencies(a2uiApplicationCodeList), ensure_ascii=False
        )

    @tool("render_application", args_schema=RenderArgs)
    def render_application(
        appCode: str, params: dict[str, Any], runtime: ToolRuntime[TrustedInvocationContext]
    ) -> Command:
        """Render a bound Application and wait only for its configured terminal Action."""
        assets.validate_context(runtime.context)
        if not runtime.tool_call_id:
            raise ActionRejected("TOOL_CALL_ID_REQUIRED")
        return actions.render(assets, appCode, params, runtime.tool_call_id)

    return use_skill, execute_ability, query_skill_dependencies, render_application


class RpcWorkflowHost(MvpRuntimeHost):
    def __init__(
        self, *, rpc: RpcClient, completion_observer: CompletionObserver, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self.rpc = rpc
        self.reader = RpcAssetReader(self.asset_repository, kwargs["namespace"], rpc)
        self.card_store = ChatCardStore(
            kwargs["conninfo"],
            environment=self.environment,
            completion_observer=completion_observer,
        )

    def _actions(self, run: Any) -> WorkflowActions:
        definition = self.reader.resolve_workflow(run.definition_key, run.owner).definition
        return WorkflowActions(
            self.interactions,
            self.lifecycle,
            self.card_store,
            self.reader,
            self.rpc,
            run,
            {node["nodeId"]: node["skillKey"] for node in definition["nodes"]},
        )

    @contextmanager
    def execution_session(self, owner: Any) -> Iterator[ExecutionSession]:
        models: list[Any] = []
        built: dict[str, WorkflowActions] = {}
        with self._checkpointer_factory() as saver:

            def graph_factory(run: Any, lifecycle: Any) -> tuple[Any, dict[str, Any]]:
                definition = self.reader.resolve_workflow(run.definition_key, run.owner).definition
                actions = self._actions(run)
                agents = {}
                schemas = {
                    "use_skill": UseSkillModelArgs,
                    "execute_ability": AbilityModelArgs,
                    "query_skill_dependencies": QuerySkillDependenciesModelArgs,
                    "render_application": RenderModelArgs,
                }
                for node in definition["nodes"]:
                    assets = actions.assets(node["nodeId"])
                    material = self.reader.load_skill(node["skillKey"], run.context(node["nodeId"]))
                    required = tuple(dict.fromkeys(("use_skill", *material.required_tool_names)))
                    allowed = set(required)
                    if "render_application" in allowed:
                        allowed.add("query_skill_dependencies")
                    available = {item.name: item for item in tools_for(assets, actions)}
                    if not allowed <= available.keys():
                        raise ActionRejected("SKILL_TOOL_BINDING_MISMATCH")
                    model = self.model_factory.create(self.model_reference, run.owner)
                    models.append(model)
                    agents[node["nodeId"]] = build_engine(
                        model,
                        [available[name] for name in sorted(allowed)],
                        {name: schemas[name].model_validate for name in allowed},
                        required,
                        harness_profile_key=model.configuration.harness_profile_key,
                        terminal_guard=actions.assert_finalizable,
                        run_lifecycle=lifecycle,
                        progress=self.progress,
                        node_context=run.context(node["nodeId"]),
                        system_prompt=self._system_prompt(node, required),
                        personal_memory=self.personal_memory,
                    )

                def predecessor_context(node_ids: list[str]) -> list[JsonObject]:
                    # Final text is already provided by NodeBoundary. Add only saved
                    # business facts, without demo-specific selectedOption assumptions.
                    results: list[JsonObject] = []
                    with self.interactions.scope(run.owner, run.run_id):
                        for node_id in node_ids:
                            for item in self.interactions.for_node(run.owner, run.run_id, node_id):
                                if item.phase != "COMPLETED" or not item.resume_consumed:
                                    raise ActionRejected("PREDECESSOR_CONTEXT_UNAVAILABLE")
                                for attempt in item.attempts:
                                    if attempt.business_success and attempt.result_json is not None:
                                        results.append(
                                            {
                                                "nodeId": node_id,
                                                "interactionId": item.interaction_id,
                                                "applicationKey": item.application_key,
                                                "actionName": attempt.request.action_name,
                                                "result": json.loads(attempt.result_json),
                                            }
                                        )
                    return results

                graph = compose_workflow(
                    run,
                    lifecycle,
                    definition,
                    agents,
                    self.views,
                    predecessor_context,
                    saver,
                )
                actions.continuation = LangGraphContinuation(graph, lifecycle=lifecycle)
                built[run.run_id] = actions
                inputs = validate_workflow_inputs(json.loads(run.initial_inputs_json))
                return graph, {"messages": [{"role": "user", "content": inputs["requirement"]}]}

            runner = ControlledRunRunner(
                self.lifecycle,
                graph_factory,
                lambda current_owner, key: self.reader.versions(current_owner, key),
            )

            def action_service(run: Any) -> WorkflowActions:
                if run.run_id not in built:
                    graph_factory(run, self.lifecycle)
                return built[run.run_id]

            try:
                yield ExecutionSession(runner, action_service)
            finally:
                for model in reversed(models):
                    _close_model(model)

    def create_app(self) -> Any:
        executions = _Lane(1)
        wrapped = create_mvp_app(
            self.service,
            self.views,
            self.workflow_catalog,
            self._owner,
            lifespan=self.lifespan,
            static_directory=self.static_directory,
            unexpected_error_observer=self.unexpected_error_observer,
            execution_capacity=1,
            execution_lane=executions,
        )
        app = wrapped.app
        reads = _Lane(2)

        @app.get("/runtime/runs/{run_id}/cards")
        async def cards(request: Request, run_id: str) -> Any:
            owner = self._owner(request.scope)

            def read() -> dict[str, Any]:
                run = self.lifecycle.read(owner, run_id)
                return {"cards": self._actions(run).list_cards()}

            return await reads.call(read, timeout=3)

        @app.post("/runtime/runs/{run_id}/cards/{card_id}/actions")
        async def action(request: Request, run_id: str, card_id: str, body: CardActionBody) -> Any:
            owner = self._owner(request.scope)

            def dispatch() -> Any:
                run = self.lifecycle.read(owner, run_id)
                return self._actions(run).execute_card(
                    body.nodeId,
                    body.interactionId,
                    card_id,
                    body.requestId,
                    body.actionName,
                    body.inputs,
                )

            return await executions.call(dispatch)

        @app.post("/runtime/runs/{run_id}/cards/{card_id}/resume")
        async def resume(request: Request, run_id: str, card_id: str, body: CardResumeBody) -> Any:
            owner = self._owner(request.scope)

            def dispatch() -> dict[str, str]:
                run = self.lifecycle.read(owner, run_id)
                with self.execution_session(owner) as session:
                    actions = session.action_service(run)
                    actions.resume_card(body.nodeId, body.interactionId, card_id, body.requestId)
                return {"runId": run_id, "delivery": "RETURNED"}

            return await executions.call(dispatch)

        return wrapped
