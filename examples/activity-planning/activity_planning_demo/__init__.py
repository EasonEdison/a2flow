"""Real local demo operations. Confirmation is Action-only, never a model Tool."""
from skillweave_contracts import TrustedContext
from capability_registry import AdapterOperationDescriptor

BUDGET_KEY = "activity-planning.budget"
CONFIRM_KEY = "activity-planning.confirm"
CONFIRM_OPERATION = "activity-planning.select"
APPLICATION_KEY = "activity-planning.confirm"
COMPONENT_KEY = "activity-planning.basic"
WORKFLOW_KEY = "activity-planning"
PROFILE = "a2flow.mvp08.v1"
PACKAGE_SELECT_ABILITY_KEY = "activity-package.select"
PACKAGE_SELECT_OPERATION = "activity-package.select"
PACKAGE_SCHEDULE_ABILITY_KEY = "activity-package.confirm-schedule"
PACKAGE_SCHEDULE_OPERATION = "activity-package.confirm-schedule"
PACKAGE_CHOOSE_APPLICATION_KEY = "activity-package.choose-plan"
PACKAGE_SCHEDULE_APPLICATION_KEY = "activity-package.confirm-schedule"
PACKAGE_DISPLAY_APPLICATION_KEY = "activity-package.display"
PACKAGE_COMPONENT_KEY = "activity-package.basic"
PACKAGE_WORKFLOW_KEY = "activity-package-demo"
PACKAGE_APPLICATION_KEYS = frozenset({PACKAGE_CHOOSE_APPLICATION_KEY,
                                      PACKAGE_SCHEDULE_APPLICATION_KEY,
                                      PACKAGE_DISPLAY_APPLICATION_KEY})
MODEL_ABILITY_KEYS = frozenset({BUDGET_KEY})


def _owner(owner):
    if type(owner) is not TrustedContext:
        raise ValueError("TRUSTED_CONTEXT_REQUIRED")


def budget_activity(arguments, owner):
    """Split a supplied minor-unit demo budget; does not obtain vendor quotes."""
    _owner(owner)
    if type(arguments) is not dict or set(arguments) != {"participants", "budgetMinor"}:
        raise ValueError("INVALID_BUDGET_ARGUMENTS")
    people, budget = arguments["participants"], arguments["budgetMinor"]
    if type(people) is not int or not 1 <= people <= 100000:
        raise ValueError("INVALID_PARTICIPANTS")
    if type(budget) is not int or not 0 <= budget <= 10**12:
        raise ValueError("INVALID_BUDGET")
    quotient, remainder = divmod(budget, people)
    return {"participants": people, "budgetMinor": budget,
            "perPersonMinor": quotient, "remainderMinor": remainder}


def select_activity(arguments, owner):
    """Return a local confirmation after Runtime validates its saved option set.

    This pure function cannot establish interaction authority. It must be bound
    only to the configured Action executor and never model execute_ability.
    """
    _owner(owner)
    if type(arguments) is not dict or set(arguments) != {"optionId", "confirmed"}:
        raise ValueError("INVALID_SELECTION_ARGUMENTS")
    if type(arguments["optionId"]) is not str or not 1 <= len(arguments["optionId"]) <= 128:
        raise ValueError("INVALID_OPTION")
    if arguments["confirmed"] is not True:
        raise ValueError("CONFIRMATION_REQUIRED")
    return {"selectedOptionId": arguments["optionId"], "confirmed": True}


def choose_package_plan(arguments, owner):
    """Save one card-bound choice; Runtime establishes interaction authority."""
    _owner(owner)
    if (type(arguments) is not dict or set(arguments) != {"optionId"}
            or type(arguments["optionId"]) is not str
            or not 1 <= len(arguments["optionId"]) <= 128):
        raise ValueError("INVALID_SELECTION_ARGUMENTS")
    return {"selectedOptionId": arguments["optionId"]}


def confirm_package_schedule(arguments, owner):
    """Save one card-bound schedule confirmation without external side effects."""
    _owner(owner)
    if (type(arguments) is not dict or set(arguments) != {"optionId", "confirmed"}
            or type(arguments["optionId"]) is not str
            or not 1 <= len(arguments["optionId"]) <= 128
            or arguments["confirmed"] is not True):
        raise ValueError("INVALID_CONFIRMATION_ARGUMENTS")
    return {"selectedOptionId": arguments["optionId"], "confirmed": True}


OPERATION_MAP = {
    BUDGET_KEY: budget_activity,
    CONFIRM_OPERATION: select_activity,
    PACKAGE_SELECT_OPERATION: choose_package_plan,
    PACKAGE_SCHEDULE_OPERATION: confirm_package_schedule,
}


class OperationCatalog:
    """Trusted allowlisted authored-operation metadata, no executable asset code."""
    def lookup(self, operation_ref):
        paths = {
            BUDGET_KEY: frozenset({"/participants", "/budgetMinor"}),
            CONFIRM_OPERATION: frozenset({"/optionId", "/confirmed"}),
            PACKAGE_SELECT_OPERATION: frozenset({"/optionId"}),
            PACKAGE_SCHEDULE_OPERATION: frozenset({"/optionId", "/confirmed"}),
        }
        if operation_ref not in paths:
            return None
        return AdapterOperationDescriptor(operation_ref, paths[operation_ref], frozenset())


def _object(properties):
    return {"type": "object", "additionalProperties": False,
            "required": list(properties), "properties": properties}


def ability_definition(key):
    """Local authored payload uses the existing Capability validator field names."""
    if key == BUDGET_KEY:
        arguments = {"participants": {"type": "integer", "minimum": 1, "maximum": 100000},
                     "budgetMinor": {"type": "integer", "minimum": 0, "maximum": 10**12}}
        output = {**arguments, "perPersonMinor": {"type": "integer", "minimum": 0},
                  "remainderMinor": {"type": "integer", "minimum": 0}}
        operation, policy = BUDGET_KEY, {
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
            "policyRef": "validBudget", "operator": "SCHEMA_VALID"}
    elif key == CONFIRM_KEY:
        arguments = {"optionId": {"type": "string", "minLength": 1, "maxLength": 128},
                     "confirmed": {"type": "boolean", "enum": [True]}}
        output = {"selectedOptionId": arguments["optionId"], "confirmed": arguments["confirmed"]}
        operation, policy = CONFIRM_OPERATION, {
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1", "policyRef": "confirmed",
            "operator": "JSON_POINTER_EQUALS", "jsonPointer": "/confirmed", "expectedLiteral": True}
    elif key == PACKAGE_SELECT_ABILITY_KEY:
        arguments = {"optionId": {"type": "string", "minLength": 1, "maxLength": 128}}
        output = {"selectedOptionId": arguments["optionId"]}
        operation, policy = PACKAGE_SELECT_OPERATION, {
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
            "policyRef": "validSelection", "operator": "SCHEMA_VALID"}
    elif key == PACKAGE_SCHEDULE_ABILITY_KEY:
        arguments = {
            "optionId": {"type": "string", "minLength": 1, "maxLength": 128},
            "confirmed": {"type": "boolean", "enum": [True]},
        }
        output = {
            "selectedOptionId": arguments["optionId"],
            "confirmed": arguments["confirmed"],
        }
        operation, policy = PACKAGE_SCHEDULE_OPERATION, {
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1", "policyRef": "confirmed",
            "operator": "JSON_POINTER_EQUALS", "jsonPointer": "/confirmed",
            "expectedLiteral": True}
    else:
        raise ValueError("UNKNOWN_DEMO_ABILITY")
    return {
        "abilityKey": key, "adapterOperationRef": operation,
        "modelArgumentSchema": _object(arguments), "resolvedInputSchema": _object(arguments),
        "outputSchema": _object(output), "credentialRequirements": [],
        "inputBindings": [{"targetPath": "/" + name, "source": "MODEL_ARGUMENT",
                           "sourcePath": "/" + name} for name in arguments],
        "resultInterpretationPolicies": [policy], "defaultSuccessPolicyRef": policy["policyRef"],
    }


def component_definition():
    return {"catalogKey": COMPONENT_KEY, "protocolProfileRef": PROFILE,
            "components": ["Column", "Text", "ChoicePicker", "Button"]}


def application_definition():
    """Small reviewed-profile candidate; no arbitrary action or component code."""
    return {
        "asset": {"kind": "APPLICATION", "applicationKey": APPLICATION_KEY,
                  "protocolProfileRef": PROFILE, "componentCatalogRef": COMPONENT_KEY},
        "renderPolicy": {"tool": "render_application", "interactionMode": "INTERACTIVE",
                         "requiresPause": True},
        "interactionPolicy": {"bindingScope": "RUNTIME_NODE_CARD_FORM",
                              "ordinaryChatMayResume": False,
                              "routeDirectlyWithoutAiReselection": True},
        "versionAdmissionPolicy": {"compareBeforeExecution": True, "compareBeforeContinue": True,
                                  "compareBeforeAction": True, "onMismatch": "RESET_REQUIRED"},
        "actionPolicies": [{"actionName": "confirm_activity", "sourceComponentId": "confirm",
                            "abilityReleaseRef": CONFIRM_KEY + "@v1", "successPolicyRef": "confirmed",
                            "completeInteractionOnSuccess": True, "controlRequestDedupeOnly": True,
                            "businessIdempotencyOwner": "CALLED_API_BACKEND"}],
        "retryPolicy": {"allowedReasons": ["RENDER_FAILED", "ACTION_CALL_FAILED",
                                         "ACTION_RESULT_NOT_SUCCESS"]},
        "finalizerPolicy": {"mayOverrideBusinessFacts": False, "mayBypassRequiredInteraction": False},
        "surfaceTemplate": {
            "surfaceKey": "activity_selection", "rootId": "root",
            "inputSchema": {
                "type": "object", "required": ["prompt", "options"], "additionalProperties": False,
                "properties": {
                    "prompt": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "options": {"type": "array", "minItems": 2, "maxItems": 8, "items":
                        _object({"label": {"type": "string", "minLength": 1, "maxLength": 2000},
                                 "value": {"type": "string", "minLength": 1, "maxLength": 128}})},
                    "optionId": {"type": "string", "minLength": 1, "maxLength": 128}}},
            "components": [
                {"id": "root", "component": "Column", "children": ["prompt", "selection", "confirm"]},
                {"id": "prompt", "component": "Text", "text": {"path": "/prompt"}},
                {"id": "selection", "component": "ChoicePicker", "options": {"path": "/options"},
                 "value": {"path": "/optionId"}, "variant": "mutuallyExclusive"},
                {"id": "confirm", "component": "Button", "label": "确认这个方案",
                 "action": {"event": {"name": "confirm_activity",
                            "context": {"optionId": {"path": "/optionId"}, "confirmed": {"literal": True}}}}},
            ],
        },
    }


from .package_demo import (
    application_definition as package_application_definition,
    component_definition as package_component_definition,
    data_validator as package_data_validator,
)


def application_validator(value):
    # Closed reviewed profiles only, not a permissive generic validator.
    from a2flow_asset_store.records import canonical
    expected = [application_definition(), *(package_application_definition(key)
                for key in sorted(PACKAGE_APPLICATION_KEYS))]
    return any(canonical(value) == canonical(item) for item in expected)


def component_validator(value):
    from a2flow_asset_store.records import canonical
    return any(canonical(value) == canonical(item)
               for item in (component_definition(), package_component_definition()))


def application_data_validator(application, value):
    return package_data_validator(application, value)


def bundle_validator():
    from a2flow_asset_store import BundleValidator
    return BundleValidator(OperationCatalog(), application_validator=application_validator,
                           component_validator=component_validator)
