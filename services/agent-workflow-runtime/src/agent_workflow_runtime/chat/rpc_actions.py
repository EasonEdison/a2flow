"""Execute only an action declared on an authenticated, persisted RPC card."""
from __future__ import annotations

import logging
from contextlib import AbstractContextManager, nullcontext
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any, TypedDict, cast

from skillweave_contracts import TrustedContext

from ..models import ActionRejected
from ..rpc_client import ComposerDraftEffect, RpcFailure
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
        if card["display"].get("protocolProfile") != "a2flow.java-rpc.v1":
            raise ActionRejected("RPC_PUBLICATION_REQUIRED")
        if (type(inputs) is not dict or set(inputs) != {"surfaceId", "sourceComponentId", "context"}
                or type(inputs["context"]) is not dict):
            raise ActionRejected("INVALID_ACTION_INPUT")
        prior = self.store.replay(owner, conversation_id, card_id, request_id,
                                  action_name, inputs)
        if prior is not None:
            return _response(prior, request_id)
        assets = self.assets_factory(owner, conversation_id)
        assets.admit_skill(metadata["skillKey"])
        action_descriptions = assets.action_descriptions()
        _, description = assets.application_description(card["display"]["applicationKey"])
        matching = [action for action in description.actions
                    if action.action_name == action_name
                    and action.surface_id == inputs["surfaceId"]
                    and action.component_id == inputs["sourceComponentId"]]
        if len(matching) != 1:
            raise ActionRejected("ACTION_NOT_BOUND")
        persisted = trusted_card(owner, card, metadata)
        with dispatch_admission() if dispatch_admission is not None else nullcontext():
            claim = self.store.claim(owner, conversation_id, card_id, request_id,
                                     action_name, inputs)
        if not claim["dispatch"]:
            return _response(cast(dict[str, Any], claim["card"]), request_id)
        # The DB claim is committed before RPC. No lock or transaction spans
        # network execution, and a timeout never triggers a business retry.
        observation: ActionObservation | None = None
        stage = "engine_act"
        try:
            result = assets.rpc.act(owner, persisted,
                                    {"version": description.catalog.protocol_version,
                                     "action": {"name": action_name, **inputs,
                                                "timestamp": datetime.now(UTC).isoformat()}},
                                    request_id, correlation_id=card_id)
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
            return _response(finished, request_id, result.composer_draft_effects)
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
