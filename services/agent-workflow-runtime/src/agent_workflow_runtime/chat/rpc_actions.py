"""Execute only an action declared on an authenticated, persisted RPC card."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, cast

from skillweave_contracts import TrustedContext

from ..application_runtime import PreparedApplication
from ..models import ActionRejected
from ..rpc_client import RpcFailure
from .cards import ActionObservation, ChatCardStore, JsonObject, JsonValue
from .rpc_assets import RpcChatAssets, plain, prepare_result, runtime_metadata, trusted_card


class RpcChatActionService:
    def __init__(self, store: ChatCardStore,
                 assets_factory: Callable[..., RpcChatAssets]) -> None:
        self.store = store
        self.assets_factory = assets_factory

    def execute(self, owner: TrustedContext, conversation_id: str, card_id: str, *,
                request_id: str, action_name: str, inputs: dict[str, Any],
                expected_revision: int) -> dict[str, Any]:
        saved = self.store.get_binding(owner, conversation_id, card_id)
        card, metadata = saved["card"], saved["metadata"]
        if card["display"].get("protocolProfile") != "a2flow.java-rpc.v1":
            raise ActionRejected("RPC_PUBLICATION_REQUIRED")
        if (type(inputs) is not dict or set(inputs) != {"surfaceId", "sourceComponentId", "context"}
                or type(inputs["context"]) is not dict):
            raise ActionRejected("INVALID_ACTION_INPUT")
        prior = self.store.replay(owner, conversation_id, card_id, request_id,
                                  action_name, inputs, expected_revision)
        if prior is not None:
            return prior
        if type(expected_revision) is not int or card["revision"] != expected_revision:
            raise ActionRejected("STALE_CARD_REVISION")
        matching = [action for action in card["display"]["actions"]
                    if action["actionName"] == action_name
                    and action["surfaceId"] == inputs["surfaceId"]
                    and action["componentId"] == inputs["sourceComponentId"]]
        if len(matching) != 1:
            raise ActionRejected("ACTION_NOT_BOUND")
        assets = self.assets_factory(owner, conversation_id)
        assets.admit_skill(metadata["skillKey"])
        assets.check_versions(metadata["recordedVersions"])
        action_descriptions = assets.action_descriptions()
        _, description = assets.application_description(card["display"]["applicationKey"])
        persisted = trusted_card(owner, card, metadata, card["revision"])
        if persisted.release != description.release:
            raise ActionRejected("RESET_REQUIRED")
        claim = self.store.claim(owner, conversation_id, card_id, request_id,
                                 action_name, inputs, expected_revision)
        if not claim["dispatch"]:
            return cast(dict[str, Any], claim["card"])
        # The DB claim is committed before RPC. No lock or transaction spans
        # network execution, and a timeout never triggers a business retry.
        observation: ActionObservation | None = None
        try:
            result = assets.rpc.act(owner, persisted,
                                    {"version": persisted.session.protocol_version,
                                     "action": {"name": action_name, **inputs,
                                                "timestamp": datetime.now(timezone.utc).isoformat()}},
                                    request_id, correlation_id=card_id)
            observed = result.action_observation
            if observed is None:
                return self.store.fail(owner, conversation_id, card_id, request_id,
                                       "ACTION_OUTCOME_UNKNOWN")
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
                return self.store.fail(owner, conversation_id, card_id, request_id,
                                       "ACTION_PRESENTATION_FAILED",
                                       observation=observation)
            updated_metadata = {**metadata, "rpc": runtime_metadata(result)}
            prepared = prepare_result(result, card["display"]["applicationVersion"])
            return self.store.finish(owner, conversation_id, card_id, request_id,
                                     plain(observed.result),
                                     result.business_success, result.complete_interaction,
                                     prepared=prepared, binding_metadata=updated_metadata,
                                     observation=observation)
        except RpcFailure as error:
            if error.code == "RESET_REQUIRED":
                # The RPC contract guarantees this precondition precedes any
                # business dispatch. Save a rejected outcome, not unknown success.
                prepared = PreparedApplication(card["display"]["applicationKey"],
                    card["display"]["applicationVersion"], description.interaction_mode == "INTERACTIVE",
                    json.dumps(card["display"], ensure_ascii=False, allow_nan=False))
                self.store.finish(owner, conversation_id, card_id, request_id,
                                  {"errorCode": "RESET_REQUIRED"}, False, False,
                                  prepared=prepared, binding_metadata=metadata,
                                  observation_status="REJECTED")
                raise
            self.store.fail(
                owner, conversation_id, card_id, request_id,
                "ACTION_OUTCOME_UNKNOWN", observation=observation,
            )
            raise ActionRejected("ACTION_OUTCOME_UNKNOWN") from None
        except Exception:
            self.store.fail(
                owner, conversation_id, card_id, request_id,
                "ACTION_OUTCOME_UNKNOWN", observation=observation,
            )
            raise ActionRejected("ACTION_OUTCOME_UNKNOWN") from None
