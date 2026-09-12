"""Closed Application profiles for the additive three-node activity package demo."""

from . import (
    APPLICATION_KEY,
    PACKAGE_CHOOSE_APPLICATION_KEY,
    PACKAGE_COMPONENT_KEY,
    PACKAGE_DISPLAY_APPLICATION_KEY,
    PACKAGE_SCHEDULE_ABILITY_KEY,
    PACKAGE_SCHEDULE_APPLICATION_KEY,
    PACKAGE_SELECT_ABILITY_KEY,
    PROFILE,
    _object,
)


def component_definition():
    return {"catalogKey": PACKAGE_COMPONENT_KEY, "protocolProfileRef": PROFILE,
            "components": ["Column", "Text", "ChoicePicker", "Button"]}


def _interactive(key, action_name, ability_key, label, *, confirmed):
    context = {"optionId": {"path": "/optionId"}}
    if confirmed:
        context["confirmed"] = {"literal": True}
    return {
        "asset": {"kind": "APPLICATION", "applicationKey": key,
                  "protocolProfileRef": PROFILE,
                  "componentCatalogRef": PACKAGE_COMPONENT_KEY},
        "renderPolicy": {"tool": "render_application", "interactionMode": "INTERACTIVE",
                         "requiresPause": True},
        "interactionPolicy": {"bindingScope": "RUNTIME_NODE_CARD_FORM",
                              "ordinaryChatMayResume": False,
                              "routeDirectlyWithoutAiReselection": True},
        "versionAdmissionPolicy": {"compareBeforeExecution": True,
                                   "compareBeforeContinue": True,
                                   "compareBeforeAction": True,
                                   "onMismatch": "RESET_REQUIRED"},
        "actionPolicies": [{"actionName": action_name, "sourceComponentId": "submit",
                            "abilityReleaseRef": ability_key + "@v1",
                            "successPolicyRef": "confirmed" if confirmed else "validSelection",
                            "completeInteractionOnSuccess": True,
                            "controlRequestDedupeOnly": True,
                            "businessIdempotencyOwner": "CALLED_API_BACKEND"}],
        "retryPolicy": {"allowedReasons": []},
        "finalizerPolicy": {"mayOverrideBusinessFacts": False,
                            "mayBypassRequiredInteraction": False},
        "surfaceTemplate": {
            "surfaceKey": key.rsplit(".", 1)[-1].replace("-", "_"), "rootId": "root",
            "inputSchema": {
                "type": "object", "required": ["prompt", "options"],
                "additionalProperties": False,
                "properties": {
                    "prompt": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "options": {"type": "array", "minItems": 2, "maxItems": 8, "items":
                        _object({"label": {"type": "string", "minLength": 1, "maxLength": 2000},
                                 "value": {"type": "string", "minLength": 1,
                                           "maxLength": 128}})},
                    "optionId": {"type": "string", "minLength": 1, "maxLength": 128}}},
            "components": [
                {"id": "root", "component": "Column",
                 "children": ["prompt", "selection", "submit"]},
                {"id": "prompt", "component": "Text", "text": {"path": "/prompt"}},
                {"id": "selection", "component": "ChoicePicker",
                 "options": {"path": "/options"}, "value": {"path": "/optionId"},
                 "variant": "mutuallyExclusive"},
                {"id": "submit", "component": "Button", "label": label,
                 "action": {"event": {"name": action_name, "context": context}}},
            ],
        },
    }


def application_definition(key):
    if key == PACKAGE_CHOOSE_APPLICATION_KEY:
        return _interactive(key, "select_activity_plan", PACKAGE_SELECT_ABILITY_KEY,
                            "选择这个方案", confirmed=False)
    if key == PACKAGE_SCHEDULE_APPLICATION_KEY:
        return _interactive(key, "confirm_schedule", PACKAGE_SCHEDULE_ABILITY_KEY,
                            "确认执行安排", confirmed=True)
    if key != PACKAGE_DISPLAY_APPLICATION_KEY:
        raise ValueError("UNKNOWN_DEMO_APPLICATION")
    bindings = (
        ("title", "title"),
        ("plan", "selectedPlan"),
        ("schedule", "confirmedSchedule"),
        ("package", "packageSummary"),
    )
    return {
        "asset": {"kind": "APPLICATION", "applicationKey": key,
                  "protocolProfileRef": PROFILE,
                  "componentCatalogRef": PACKAGE_COMPONENT_KEY},
        "renderPolicy": {"tool": "render_application", "interactionMode": "DISPLAY_ONLY",
                         "requiresPause": False},
        "interactionPolicy": {"bindingScope": "RUNTIME_NODE_CARD_FORM",
                              "ordinaryChatMayResume": False,
                              "routeDirectlyWithoutAiReselection": False},
        "versionAdmissionPolicy": {"compareBeforeExecution": True,
                                   "compareBeforeContinue": True,
                                   "compareBeforeAction": True,
                                   "onMismatch": "RESET_REQUIRED"},
        "actionPolicies": [], "retryPolicy": {"allowedReasons": []},
        "finalizerPolicy": {"mayOverrideBusinessFacts": False,
                            "mayBypassRequiredInteraction": False},
        "surfaceTemplate": {
            "surfaceKey": "activity_package", "rootId": "root",
            "inputSchema": _object({path: {
                "type": "string", "minLength": 1, "maxLength": 2000,
            } for _, path in bindings}),
            "components": [
                {"id": "root", "component": "Column",
                 "children": [name for name, _ in bindings]},
                *[{"id": name, "component": "Text", "text": {"path": "/" + path}}
                  for name, path in bindings],
            ],
        },
    }


def data_validator(application, value):
    key = application["asset"]["applicationKey"]
    if key in {APPLICATION_KEY, PACKAGE_CHOOSE_APPLICATION_KEY,
               PACKAGE_SCHEDULE_APPLICATION_KEY}:
        if type(value) is not dict or set(value) != {"prompt", "options"}:
            return False
        options = value["options"]
        return (type(value["prompt"]) is str and 1 <= len(value["prompt"]) <= 2000
                and type(options) is list and 2 <= len(options) <= 8
                and all(type(option) is dict and set(option) == {"label", "value"}
                        and type(option["label"]) is str
                        and 1 <= len(option["label"]) <= 2000
                        and type(option["value"]) is str
                        and 1 <= len(option["value"]) <= 128 for option in options)
                and len({option["value"] for option in options}) == len(options))
    if key == PACKAGE_DISPLAY_APPLICATION_KEY:
        fields = {"title", "selectedPlan", "confirmedSchedule", "packageSummary"}
        return (type(value) is dict and set(value) == fields
                and all(type(item) is str and 1 <= len(item) <= 2000
                        for item in value.values()))
    return False
