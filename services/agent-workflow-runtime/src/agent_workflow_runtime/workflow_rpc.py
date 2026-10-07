"""Current RPC Skill/A2UI contracts bound to native Workflow interactions."""

from __future__ import annotations

import json
from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import replace
from hashlib import sha256
from typing import Any, Literal, TypedDict, cast

from langchain_core.messages import ToolMessage
from langgraph.types import Command, interrupt
from skill_registry import InvocationScope as RegistryScope
from skill_registry import TrustedContext as RegistryOwner
from skill_registry import TrustedInvocationContext as RegistryContext
from skillweave_contracts import CONTRACT_REVISION, TrustedInvocationContext

from .actions import ActionService
from .application_runtime import PreparedApplication
from .chat.cards import ChatCardStore, JsonObject, _card_id
from .chat.loop import _action_observation_message, _read_observations
from .chat.render_projection import project_rendered_content
from .chat.rpc_actions import ChatActionResponse, RpcChatActionService
from .chat.rpc_assets import RpcChatAssets
from .lifecycle import OperationFact, RunLifecycle, RunRecord
from .models import ActionRejected, ActionRequest, Attempt, Interaction
from .ports import InteractionRepository
from .rpc_client import RpcClient
from .rpc_assets import RpcAssetReader


def card_scope(run_id: str, node_id: str) -> str:
    return "workflow:" + sha256(json.dumps([run_id, node_id]).encode()).hexdigest()


class ResumeStatus(TypedDict):
    runId: str
    delivery: Literal["NOT_REQUESTED", "DISPATCHING", "UNCONFIRMED", "RETURNED"]
    resumeConsumed: bool


class WorkflowCard(TypedDict):
    nodeId: str
    interactionId: str
    card: dict[str, Any]


class WorkflowAssets(RpcChatAssets):
    """Reuse published contracts, with identity fixed to one compiled node."""

    def __init__(
        self,
        reader: RpcAssetReader,
        rpc: RpcClient,
        run: RunRecord,
        node_id: str,
        skill_key: str,
        store: ChatCardStore,
    ) -> None:
        self.run, self.node_id, self.skill_key, self.store = run, node_id, skill_key, store
        super().__init__(
            reader=reader,
            rpc=rpc,
            owner=run.owner,
            conversation_id=card_scope(run.run_id, node_id),
            control_request_id=run.context(node_id).control_request_id,
            card_sink=self._save_card,
        )

    def _save_card(self, prepared: PreparedApplication, metadata: dict[str, Any]) -> dict[str, Any]:
        metadata["workflow"] = {"runId": self.run.run_id, "nodeId": self.node_id}
        metadata["observation"]["preparedContent"] = project_rendered_content(
            prepared.display()["snapshotMessages"],
        )
        return cast(
            dict[str, Any],
            self.store.save(
                self.owner,
                self.conversation_id,
                prepared,
                metadata,
            ),
        )

    def _registry_context(self) -> RegistryContext:
        return RegistryContext(
            contract_revision=CONTRACT_REVISION,
            trusted_context=RegistryOwner(
                user_id=self.owner.user_id, environment=self.owner.environment
            ),
            invocation_scope=RegistryScope(
                kind="WORKFLOW",
                conversation_id=None,
                run_id=self.run.run_id,
                node_id=self.node_id,
            ),
            control_request_id=self.control_request_id,
        )

    def validate_context(self, context: TrustedInvocationContext) -> TrustedInvocationContext:
        if (
            context.trusted_context != self.owner
            or context.invocation_scope.kind != "WORKFLOW"
            or context.invocation_scope.run_id != self.run.run_id
        ):
            raise ActionRejected("RUN_NODE_BINDING_MISMATCH")
        return self.run.context(self.node_id)

    def admit_skill(self, skill_key: str) -> dict[str, Any]:
        if skill_key != self.skill_key:
            raise ActionRejected("SKILL_NOT_BOUND_TO_NODE")
        return super().admit_skill(skill_key)

    def current(self) -> None:
        # A resumed graph restores use_skill's ToolMessage, not adapter objects.
        self.admit_skill(self.skill_key)

    def render_application(
        self, application_key: str, data: dict[str, Any], tool_call_id: str
    ) -> dict[str, Any]:
        self.current()
        card_id = _card_id(self.owner, self.conversation_id, self.control_request_id, tool_call_id)
        saved = self.store.read(self.owner, self.conversation_id, card_id)
        if saved is None:
            return super().render_application(application_key, data, tool_call_id)
        binding = self.store.get_binding(self.owner, self.conversation_id, card_id)
        metadata = binding["metadata"]
        if (
            metadata["applicationKey"] != application_key
            or metadata["rpc"]["params"] != data
            or metadata.get("workflow") != {"runId": self.run.run_id, "nodeId": self.node_id}
        ):
            raise ActionRejected("CARD_REPLAY_CONFLICT")
        return cast(dict[str, Any], saved)

    def saved_render_observation(self, card_id: str) -> JsonObject:
        binding = self.store.get_binding(self.owner, self.conversation_id, card_id)
        metadata = binding["metadata"]
        # Original display observation stays stable across Action updates.
        return {
            "cardId": card_id,
            "appCode": metadata["applicationKey"],
            "arguments": metadata["observation"]["arguments"],
            "preparedContent": metadata["observation"]["preparedContent"],
            "visibility": "Prepared and saved; this does not assert the user viewed it.",
        }


class WorkflowActions(ActionService):
    """Business execution belongs to RPC; only saved terminal facts resume nodes."""

    def __init__(
        self,
        repository: InteractionRepository,
        lifecycle: RunLifecycle,
        store: ChatCardStore,
        reader: RpcAssetReader,
        rpc: RpcClient,
        run: RunRecord,
        skills: dict[str, str],
    ) -> None:
        # The inherited register/completion/finalizer retain native guard semantics.
        super().__init__(repository, None, None, None, lifecycle=lifecycle)
        self.store, self.reader, self.rpc, self.run, self.skills = store, reader, rpc, run, skills

    def assets(self, node_id: str) -> WorkflowAssets:
        skill = self.skills.get(node_id)
        if skill is None:
            raise ActionRejected("NODE_NOT_FOUND")
        return WorkflowAssets(self.reader, self.rpc, self.run, node_id, skill, self.store)

    def list_cards(self) -> list[WorkflowCard]:
        result: list[WorkflowCard] = []
        active = self.lifecycle.read(self.run.owner, self.run.run_id).status == "RUNNING"
        for node_id in self.skills:
            for card in self.store.list(self.run.owner, card_scope(self.run.run_id, node_id)):
                if not active:
                    card["status"] = "DISPLAY_ONLY"
                    card["display"]["actions"] = []
                result.append({"nodeId": node_id, "interactionId": card["cardId"], "card": card})
        return result

    def binding(self, node_id: str, interaction_id: str, card_id: str) -> dict[str, Any]:
        self.assets(node_id)
        if interaction_id != card_id:
            raise ActionRejected("CARD_BINDING_MISMATCH")
        binding = self.store.get_binding(
            self.run.owner,
            card_scope(self.run.run_id, node_id),
            card_id,
        )
        if binding["metadata"].get("workflow") != {
            "runId": self.run.run_id,
            "nodeId": node_id,
        }:
            raise ActionRejected("CARD_BINDING_MISMATCH")
        return cast(dict[str, Any], binding)

    def execute_card(
        self,
        node_id: str,
        interaction_id: str,
        card_id: str,
        request_id: str,
        action_name: str,
        inputs: dict[str, Any],
    ) -> ChatActionResponse:
        self.binding(node_id, interaction_id, card_id)
        self.lifecycle.assert_active(self.run.owner, self.run.run_id)
        service = RpcChatActionService(
            self.store,
            lambda owner, conversation: self.assets(node_id),
        )
        admissions: list[OperationFact] = []

        @contextmanager
        def admit() -> Iterator[None]:
            with self.lifecycle.admission(
                self.run.owner,
                self.run.run_id,
                node_id,
                "ACTION",
            ) as operation:
                admissions.append(operation)
                yield

        try:
            response = service.execute(
                self.run.owner,
                card_scope(self.run.run_id, node_id),
                card_id,
                request_id=request_id,
                action_name=action_name,
                inputs=inputs,
                dispatch_admission=admit,
            )
        except BaseException:
            for operation in admissions:
                self.lifecycle.finish(
                    self.run.owner,
                    self.run.run_id,
                    operation.operation_id,
                    None,
                    status="UNCONFIRMED",
                )
            raise
        for operation in admissions:
            self.lifecycle.finish(self.run.owner, self.run.run_id, operation.operation_id, response)
        return response

    def resume_card(
        self,
        node_id: str,
        interaction_id: str,
        card_id: str,
        request_id: str,
        action_request_id: str,
    ) -> None:
        binding = self.binding(node_id, interaction_id, card_id)
        scope = card_scope(self.run.run_id, node_id)
        facts = _read_observations(
            lambda after: self.store.list_observations(
                self.run.owner,
                scope,
                after_sequence=after,
            ),
            0,
        )
        matches = [
            fact
            for fact in facts
            if fact.kind == "ACTION"
            and fact.card_id == card_id
            and fact.request_id == action_request_id
        ]
        if (
            binding["card"]["status"] != "COMPLETED"
            or binding["metadata"].get("workflowCompletionRequestId") != action_request_id
            or len(matches) != 1
            or matches[0].status != "SUCCEEDED"
            or matches[0].business_success is not True
        ):
            raise ActionRejected("INTERACTION_NOT_COMPLETED")
        fact = matches[0]
        key = (self.run.run_id, node_id, interaction_id)
        with self.repository.scope(self.run.owner, self.run.run_id):
            saved = self._get(key, self.run.owner)
            if saved.resume_started:
                if saved.completion_request_id != request_id:
                    raise ActionRejected("CONTROL_REQUEST_CONFLICT")
                prior = [
                    attempt
                    for attempt in saved.attempts
                    if attempt.request.control_request_id == request_id
                ]
                if len(prior) == 1 and prior[0].resume_status == "RETURNED":
                    return
                raise ActionRejected("RESUME_UNCONFIRMED")
            self._active(saved, self.run.owner)
            request = ActionRequest(
                self.run.run_id,
                node_id,
                interaction_id,
                fact.action_name or "",
                request_id,
                json.dumps(fact.arguments or {}, ensure_ascii=False),
            )
            attempt = Attempt(
                request,
                "EXECUTED",
                True,
                True,
                json.dumps(fact.result, ensure_ascii=False),
                "DISPATCHING",
            )
            saved = replace(
                saved,
                phase="COMPLETED",
                resume_started=True,
                completion_request_id=request_id,
                attempts=(*saved.attempts, attempt),
            )
            self.repository.save(saved)
        with self.repository.continuation_scope(self.run.owner, self.run.run_id):
            try:
                self._run_active(self.run.owner, self.run.run_id)
                self.continuation(saved, request_id)
            except Exception:
                self._delivery_status(request, "UNCONFIRMED", self.run.owner)
                raise
            self._delivery_status(request, "RETURNED", self.run.owner)

    def resume_status(
        self,
        node_id: str,
        interaction_id: str,
        card_id: str,
        request_id: str,
        action_request_id: str,
    ) -> ResumeStatus:
        binding = self.binding(node_id, interaction_id, card_id)
        if (
            binding["card"]["status"] != "COMPLETED"
            or binding["metadata"].get("workflowCompletionRequestId") != action_request_id
        ):
            raise ActionRejected("INTERACTION_NOT_COMPLETED")
        key = (self.run.run_id, node_id, interaction_id)
        with self.repository.scope(self.run.owner, self.run.run_id):
            saved = self._get(key, self.run.owner)
        if not saved.resume_started:
            return {"runId": self.run.run_id, "delivery": "NOT_REQUESTED", "resumeConsumed": False}
        if saved.completion_request_id != request_id:
            raise ActionRejected("CONTROL_REQUEST_CONFLICT")
        attempts = [
            attempt
            for attempt in saved.attempts
            if attempt.request.control_request_id == request_id
        ]
        if len(attempts) != 1:
            raise ActionRejected("RESUME_FACT_UNAVAILABLE")
        status = attempts[0].resume_status
        if status not in {"DISPATCHING", "UNCONFIRMED", "RETURNED"}:
            raise ActionRejected("RESUME_FACT_UNAVAILABLE")
        return {
            "runId": self.run.run_id,
            "delivery": cast(Literal["DISPATCHING", "UNCONFIRMED", "RETURNED"], status),
            "resumeConsumed": saved.resume_consumed,
        }

    def render(
        self, assets: WorkflowAssets, app_code: str, params: dict[str, Any], tool_call_id: str
    ) -> Command:
        card = assets.render_application(app_code, params, tool_call_id)
        context = assets.run.context(assets.node_id)
        key = (self.run.run_id, assets.node_id, card["cardId"])
        with self.repository.scope(self.run.owner, self.run.run_id):
            saved = self.repository.get(key, self.run.owner)
        if saved is None:
            interactive = card["status"] == "WAITING_ACTION"
            saved = Interaction(
                context,
                card["cardId"],
                app_code,
                card["display"]["applicationVersion"],
                self.run.thread_id,
                self.run.versions,
                display_json=json.dumps(
                    {
                        **card["display"],
                        "cardId": card["cardId"],
                        "interactionId": card["cardId"],
                        "nodeId": assets.node_id,
                    },
                    ensure_ascii=False,
                ),
                phase="WAITING" if interactive else "COMPLETED",
                node_waiting=interactive,
                resume_consumed=not interactive,
            )
            self.register(saved)
        messages: list[Any] = [
            ToolMessage(
                content=json.dumps(
                    {"renderedApplication": assets.saved_render_observation(card["cardId"])},
                    ensure_ascii=False,
                ),
                tool_call_id=tool_call_id,
                name="render_application",
                artifact={"cardId": card["cardId"], "appCode": app_code},
            )
        ]
        if saved.node_waiting:
            reference = {
                "kind": "A2UI_INTERACTION_REQUIRED",
                "runId": self.run.run_id,
                "nodeId": assets.node_id,
                "interactionId": saved.interaction_id,
                "applicationKey": app_code,
                "versionId": saved.application_version,
            }
            resumed = interrupt(reference)
            self.completion(key, resumed, self.run.owner)
            # One render Tool owns one card. Its saved facts are projected once
            # into the native Tool completion checkpoint before model continuation.
            facts = _read_observations(
                lambda after: self.store.list_observations(
                    self.run.owner,
                    assets.conversation_id,
                    after_sequence=after,
                ),
                0,
            )
            messages.extend(
                _action_observation_message(fact)
                for fact in facts
                if fact.kind == "ACTION" and fact.card_id == card["cardId"]
            )
        assets.begin_turn()
        return Command(update={"messages": messages})
