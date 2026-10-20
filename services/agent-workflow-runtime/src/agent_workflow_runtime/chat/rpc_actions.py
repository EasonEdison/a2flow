"""Execute only an action declared on an authenticated, persisted RPC card."""
from __future__ import annotations

import logging
from hashlib import sha256
from contextlib import AbstractContextManager, nullcontext
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any, NotRequired, TypedDict, cast

from skillweave_contracts import TrustedContext

from ..models import ActionRejected
from ..capability_approval import (approval_binding, approval_required, prepare_confirmation,
                                   receipt_for, require_confirmation)
from ..temporary_interaction import completed_interaction
from ..rpc_client import ApplicationDescription, ComposerDraftEffect, RpcFailure, TrustedCard
from .cards import ActionObservation, ChatCardStore, JsonObject, JsonValue
from .rpc_assets import RpcChatAssets, plain, prepare_result, runtime_metadata, trusted_card

LOG = logging.getLogger(__name__)


class ComposerDraftEffectPayload(TypedDict):
    type: str
    mode: str
    requestId: str
    text: str


class ChatActionResponse(TypedDict):
    card: dict[str, Any]
    effects: list[ComposerDraftEffectPayload]
    continuation: NotRequired[dict[str, str]]


def _response(
    card: dict[str, Any],
    request_id: str,
    effects: Iterable[ComposerDraftEffect] = (),
) -> ChatActionResponse:
    projected: list[ComposerDraftEffectPayload] = []
    for effect in effects:
        if (
            effect.type != "COMPOSER_DRAFT"
            or effect.mode != "APPEND"
            or effect.request_id != request_id
            or not effect.text
            or len(effect.text) > 4000
        ):
            raise RpcFailure("RPC_RESPONSE_INVALID")
        projected.append({
            "type": effect.type,
            "mode": effect.mode,
            "requestId": effect.request_id,
            "text": effect.text,
        })
    return {"card": card, "effects": projected}


class RpcChatActionService:
    def __init__(self, store: ChatCardStore,
                 assets_factory: Callable[..., RpcChatAssets]) -> None:
        self.store = store
        self.assets_factory = assets_factory

    def execute(self, owner: TrustedContext, conversation_id: str, card_id: str, *,
                request_id: str, action_name: str, inputs: dict[str, Any],
                dispatch_admission: Callable[[], AbstractContextManager[Any]] | None = None,
                ) -> ChatActionResponse:
        saved = self.store.get_binding(owner, conversation_id, card_id)
        card, metadata = saved["card"], saved["metadata"]
        if "approval" in metadata:
            return self._approve(owner, conversation_id, card_id, request_id, action_name,
                                 inputs, card, metadata, dispatch_admission)
        if card["display"].get("protocolProfile") == "a2flow.temporary.v1":
            with dispatch_admission() if dispatch_admission is not None else nullcontext():
                completed = self.store.submit_interaction(
                    owner, conversation_id, card_id, request_id, action_name, inputs,
                )
            response = _response(completed, request_id)
            if "workflow" not in metadata:
                response["continuation"] = {"cardId": card_id, "requestId": request_id}
            return response
        if card["display"].get("protocolProfile") != "a2flow.java-rpc.v1":
            raise ActionRejected("RPC_PUBLICATION_REQUIRED")
        prior = self.store.replay(owner, conversation_id, card_id, request_id,
                                  action_name, inputs)
        if prior is not None:
            response = _response(prior, request_id)
            completed_approval = metadata.get("completedApproval", {})
            if (prior["status"] == "COMPLETED" and "workflow" not in metadata
                    and completed_approval.get("confirmationRequestId") == request_id):
                response["continuation"] = {"cardId": card_id, "requestId": request_id,
                                            "kind": "WRITE_APPROVAL"}
            return response
        if (type(inputs) is not dict or set(inputs) != {"surfaceId", "sourceComponentId", "context"}
                or type(inputs["context"]) is not dict):
            raise ActionRejected("INVALID_ACTION_INPUT")
        assets = self.assets_factory(owner, conversation_id)
        assets.admit_skill(metadata["skillKey"])
        action_descriptions = assets.action_descriptions()
        _, description = assets.application_description(card["display"]["applicationKey"])
        persisted = trusted_card(owner, card, metadata)
        if persisted.generated_definition is not None:
            # IDs belong to the saved generated layout; business permission still
            # belongs to the currently approved origin. RPC validates the binding.
            matching = [action for action in card["display"]["actions"]
                        if action["actionName"] == action_name
                        and action["surfaceId"] == inputs["surfaceId"]
                        and action["componentId"] == inputs["sourceComponentId"]]
            if not any(action.action_name == action_name for action in description.actions):
                raise ActionRejected("ACTION_NOT_BOUND")
        else:
            matching = [action for action in description.actions
                        if action.action_name == action_name
                        and action.surface_id == inputs["surfaceId"]
                        and action.component_id == inputs["sourceComponentId"]]
        if len(matching) != 1:
            raise ActionRejected("ACTION_NOT_BOUND")
        action_message = {"version": description.catalog.protocol_version,
                          "action": {"name": action_name, **inputs,
                                     "timestamp": datetime.now(UTC).isoformat()}}
        preflight = assets.rpc.prepare_action(owner, persisted, action_message, request_id,
                                             correlation_id=card_id)
        if approval_required(preflight.description):
            prepared = prepare_confirmation(preflight.description, preflight.arguments)
            scope = metadata.get("workflow", {}).get("runId", conversation_id)
            tool_id = "a2ui:" + sha256((card_id + "\0" + request_id).encode()).hexdigest()
            binding = approval_binding(owner, scope, tool_id, preflight.description.asset_key,
                                       preflight.arguments, preflight.description)
            binding["actionBindingId"] = preflight.binding_id
            with dispatch_admission() if dispatch_admission is not None else nullcontext():
                waiting = self.store.prepare_action_confirmation(
                    owner, conversation_id, card_id, request_id, action_name, inputs,
                    original=saved, prepared=prepared, approval=binding,
                )
            return _response(waiting, request_id)
        with dispatch_admission() if dispatch_admission is not None else nullcontext():
            claim = self.store.claim(owner, conversation_id, card_id, request_id,
                                     action_name, inputs)
        if not claim["dispatch"]:
            return _response(cast(dict[str, Any], claim["card"]), request_id)
        return self._dispatch_rpc(owner, conversation_id, card_id, request_id,
            assets, metadata, persisted, description, action_name, inputs, action_descriptions)

    def _dispatch_rpc(
        self, owner: TrustedContext, conversation_id: str, card_id: str, request_id: str,
        assets: RpcChatAssets, metadata: dict[str, Any], persisted: TrustedCard,
        description: ApplicationDescription, action_name: str, inputs: dict[str, Any],
        action_descriptions: dict[str, str | None], *,
        approval_receipt: dict[str, Any] | None = None, continue_after_write: bool = False,
    ) -> ChatActionResponse:
        # The DB claim is committed before RPC. No lock or transaction spans
        # network execution, and a timeout never triggers a business retry.
        observation: ActionObservation | None = None
        stage = "engine_act"
        try:
            result = assets.rpc.act(owner, persisted,
                                    {"version": description.catalog.protocol_version,
                                     "action": {"name": action_name, **inputs,
                                                "timestamp": datetime.now(UTC).isoformat()}},
                                    request_id, correlation_id=card_id,
                                    **({} if approval_receipt is None else {
                                        "approval_receipt": approval_receipt}))
            stage = "response_projection"
            observed = result.action_observation
            if observed is None:
                failed = self.store.fail(owner, conversation_id, card_id, request_id,
                                         "ACTION_OUTCOME_UNKNOWN")
                return _response(failed, request_id)
            observation = ActionObservation(
                description=action_descriptions.get(observed.action_code),
                arguments=cast(JsonObject, plain(observed.arguments)),
                result=cast(JsonValue, plain(observed.result)),
                capability_success=observed.capability_success,
                business_success=observed.business_success,
                presentation_status=("FAILED" if observed.presentation_error_code
                                     else "SUCCEEDED"),
                presentation_error_code=observed.presentation_error_code,
                capability_error_code=observed.capability_error_code,
            )
            if observed.presentation_error_code:
                failed = self.store.fail(owner, conversation_id, card_id, request_id,
                                         "ACTION_PRESENTATION_FAILED",
                                         observation=observation)
                return _response(failed, request_id)
            updated_metadata = {**metadata, "rpc": runtime_metadata(result)}
            prepared = prepare_result(result)
            updated_metadata["applicationVersion"] = prepared.application_version
            stage = "card_finish"
            finished = self.store.finish(
                owner, conversation_id, card_id, request_id,
                plain(observed.result), result.business_success,
                result.complete_interaction, prepared=prepared,
                binding_metadata=updated_metadata, observation=observation,
            )
            response = _response(finished, request_id, result.composer_draft_effects)
            if continue_after_write and finished["status"] == "COMPLETED" and "workflow" not in metadata:
                response["continuation"] = {"cardId": card_id, "requestId": request_id,
                                            "kind": "WRITE_APPROVAL"}
            return response
        except RpcFailure as error:
            LOG.error(
                "rpc_chat_action_failed stage=%s exception_type=%s error_code=%s "
                "request_id=%s",
                stage,
                type(error).__name__,
                error.code,
                request_id,
            )
            self.store.fail(
                owner, conversation_id, card_id, request_id,
                "ACTION_OUTCOME_UNKNOWN", observation=observation,
            )
            raise ActionRejected("ACTION_OUTCOME_UNKNOWN") from None
        except Exception as error:
            LOG.error(
                "rpc_chat_action_failed stage=%s exception_type=%s error_code=%s "
                "request_id=%s",
                stage,
                type(error).__name__,
                "ACTION_OUTCOME_UNKNOWN",
                request_id,
            )
            self.store.fail(
                owner, conversation_id, card_id, request_id,
                "ACTION_OUTCOME_UNKNOWN", observation=observation,
            )
            raise ActionRejected("ACTION_OUTCOME_UNKNOWN") from None

    def _approve(
        self, owner: TrustedContext, conversation_id: str, card_id: str,
        request_id: str, action_name: str, inputs: dict[str, Any], card: dict[str, Any],
        metadata: dict[str, Any],
        dispatch_admission: Callable[[], AbstractContextManager[Any]] | None,
    ) -> ChatActionResponse:
        def response(value: dict[str, Any]) -> ChatActionResponse:
            result = _response(value, request_id)
            if "workflow" not in metadata and value["status"] == "COMPLETED":
                result["continuation"] = {"cardId": card_id, "requestId": request_id,
                                          "kind": "WRITE_APPROVAL"}
            return result

        prior = self.store.replay(owner, conversation_id, card_id, request_id, action_name, inputs)
        if prior is not None:
            return response(prior)
        submitted = require_confirmation(card["display"], action_name, inputs)
        if "approvalOriginRequestId" in metadata:
            return self._approve_application(owner, conversation_id, card_id, request_id,
                action_name, inputs, metadata, dispatch_admission)
        if "workflow" in metadata:
            with dispatch_admission() if dispatch_admission is not None else nullcontext():
                return response(self.store.submit_interaction(
                    owner, conversation_id, card_id, request_id, action_name, inputs))
        binding = metadata["approval"]
        receipt = receipt_for(owner, card_id, binding)
        if (receipt["run_id"] != conversation_id
                or receipt["tool_call_id"] != metadata["toolCallId"]):
            raise ActionRejected("WRITE_CONFIRMATION_BINDING_INVALID")
        assets = self.assets_factory(
            owner, conversation_id, metadata["controlRequestId"],
            processing_context=metadata.get("approvalProcessingContext"),
            processing_turn_id=metadata.get("approvalProcessingTurnId"),
        )
        assets.admit_skill(metadata["approvalSkillKey"])
        prepared = completed_interaction(card["display"], submitted)
        with dispatch_admission() if dispatch_admission is not None else nullcontext():
            claim = self.store.claim(owner, conversation_id, card_id, request_id, action_name, inputs)
        if not claim["dispatch"]:
            return response(claim["card"])
        # Only a durable user claim reaches this internal receipt-bearing call.
        try:
            value = assets.execute_ability(binding["abilityKey"], binding["arguments"],
                tool_call_id=metadata["toolCallId"], approval_receipt=receipt)
            output = value["output"]
            if metadata.get("approvalProcessingContext") is not None:
                if output.get("status") != "RETURNED":
                    return response(self.store.fail(owner, conversation_id, card_id,
                                                   request_id, "ACTION_OUTCOME_UNKNOWN"))
            observation = ActionObservation(
                description="用户已确认写操作；以下为真实业务执行回执，不得重复执行相同操作",
                arguments=binding["arguments"], result=output,
                capability_success=True, business_success=True, presentation_status="SUCCEEDED",
            )
            finished = self.store.finish(owner, conversation_id, card_id, request_id,
                output, True, True, prepared=prepared, binding_metadata=metadata,
                observation=observation)
            return response(finished)
        except Exception as error:
            LOG.error("chat_write_confirmation_failed exception_type=%s request_id=%s",
                      type(error).__name__, request_id)
            self.store.fail(owner, conversation_id, card_id, request_id, "ACTION_OUTCOME_UNKNOWN")
            raise ActionRejected("ACTION_OUTCOME_UNKNOWN") from None

    def _approve_application(
        self, owner: TrustedContext, conversation_id: str, card_id: str, request_id: str,
        action_name: str, inputs: dict[str, Any], metadata: dict[str, Any],
        dispatch_admission: Callable[[], AbstractContextManager[Any]] | None,
    ) -> ChatActionResponse:
        origin = self.store.get_approval_origin(owner, conversation_id, card_id)
        original_metadata = origin["metadata"]
        assets = self.assets_factory(owner, conversation_id)
        assets.admit_skill(original_metadata["skillKey"])
        _, description = assets.application_description(origin["card"]["display"]["applicationKey"])
        persisted = trusted_card(owner, origin["card"], original_metadata)
        identity = sha256((card_id + "\0" + metadata["approvalOriginRequestId"]).encode()).hexdigest()
        receipt = receipt_for(owner, "confirmation:" + identity, metadata["approval"])
        scope = original_metadata.get("workflow", {}).get("runId", conversation_id)
        if receipt["run_id"] != scope or receipt["tool_call_id"] != "a2ui:" + identity:
            raise ActionRejected("WRITE_CONFIRMATION_BINDING_INVALID")
        with dispatch_admission() if dispatch_admission is not None else nullcontext():
            claim = self.store.claim(owner, conversation_id, card_id, request_id, action_name, inputs)
        if not claim["dispatch"]:
            response = _response(claim["card"], request_id)
            if claim["card"]["status"] == "COMPLETED" and "workflow" not in original_metadata:
                response["continuation"] = {"cardId": card_id, "requestId": request_id,
                                            "kind": "WRITE_APPROVAL"}
            return response
        restored = {**original_metadata, "completedApproval": {
            "preflightRequestId": metadata["approvalOriginRequestId"],
            "confirmationRequestId": request_id,
        }}
        return self._dispatch_rpc(owner, conversation_id, card_id, request_id, assets, restored,
            persisted, description, origin["actionName"], origin["inputs"], assets.action_descriptions(),
            approval_receipt=receipt, continue_after_write=True)
