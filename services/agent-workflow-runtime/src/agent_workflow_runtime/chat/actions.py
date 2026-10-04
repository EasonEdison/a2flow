"""Conversation Application Actions, independent of Workflow and model turns."""

from types import SimpleNamespace

from ..ability_execution import result_policy
from ..models import ActionRejected, json_copy
from ..policy import business_succeeded


class ChatActionService:
    def __init__(self, store, assets_factory):
        self.store, self.assets_factory = store, assets_factory

    def execute(self, owner, conversation_id, card_id, *, request_id,
                action_name, inputs):
        saved = self.store.get_binding(owner, conversation_id, card_id)
        if saved is None:
            raise ActionRejected("CARD_NOT_FOUND")
        card, metadata = saved["card"], saved["metadata"]
        assets = self.assets_factory(owner, conversation_id)
        assets.admit_skill(metadata["skillKey"])
        resolved, policy, ability, operation = assets.action_binding(
            card["display"]["applicationKey"], action_name)
        if not operation.action_allowed:
            raise ActionRejected("ACTION_NOT_ALLOWED")
        safe_inputs = json_copy(inputs)
        if operation.validate_input(safe_inputs) is not True:
            raise ActionRejected("INVALID_ACTION_INPUT")
        # This slice admits the existing selection-card profile only. Never trust
        # a caller-supplied DataModel, operation reference or completion flag.
        options = card["display"]["data"].get("options", [])
        if ("optionId" in safe_inputs and safe_inputs["optionId"]
                not in {option["value"] for option in options}):
            raise ActionRejected("INVALID_ACTION_INPUT")
        completes = policy["completeInteractionOnSuccess"]
        if type(completes) is not bool:
            raise ActionRejected("INVALID_ACTION_POLICY")
        evaluation = SimpleNamespace(validate_result=operation.validate_result,
            success_policy=result_policy(ability, policy["successPolicyRef"]))
        claim = self.store.claim(owner, conversation_id, card_id, request_id,
                                 action_name, safe_inputs)
        if not claim["dispatch"]:
            return claim["card"]
        try:
            result = json_copy(operation.execute(safe_inputs, owner))
            success = business_succeeded(evaluation, result)
            return self.store.finish(owner, conversation_id, card_id, request_id,
                                     result, success, completes)
        except Exception:
            # A remote effect may already have happened. Do not retry it or tell
            # the model to repair it. The saved unknown outcome is authoritative.
            self.store.fail(owner, conversation_id, card_id, request_id,
                            "ACTION_OUTCOME_UNKNOWN")
            raise ActionRejected("ACTION_OUTCOME_UNKNOWN") from None
