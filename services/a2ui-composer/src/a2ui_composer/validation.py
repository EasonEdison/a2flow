"""Published application validation shared by asset readers and Runtime."""

from skillweave_contracts import parse_identifier

from .errors import ValidationError
from .schema import schema_path_exists, validate_input_schema

_ALLOWED_COMPONENTS = frozenset({"Column", "Text", "ChoicePicker", "Button"})
_FLOATING_VERSIONS = frozenset({"default", "draft", "latest"})
_FORBIDDEN_KEYS = frozenset(
    {
        "credential",
        "credentials",
        "environment",
        "grayTarget",
        "href",
        "html",
        "roles",
        "script",
        "src",
        "uri",
        "url",
        "userId",
    }
)
_INTERACTIVE_RETRY = frozenset(
    {
        "RENDER_FAILED",
        "ACTION_CALL_FAILED",
        "ACTION_RESULT_NOT_SUCCESS",
    }
)
_DISPLAY_POLICIES = (
    {"bindingScope": "NONE", "ordinaryChatMayResume": False},
    {
        "bindingScope": "RUNTIME_NODE_CARD_FORM",
        "ordinaryChatMayResume": False,
        "routeDirectlyWithoutAiReselection": False,
    },
)


def _closed(value, keys, code):
    if type(value) is not dict or set(value) != set(keys):
        raise ValidationError(code)


def _binding(value, *, literals=False):
    if type(value) is not dict or len(value) != 1:
        raise ValidationError("INVALID_DATA_BINDING")
    if set(value) == {"path"}:
        path = value["path"]
        if type(path) is not str or not path.startswith("/") or len(path) > 256:
            raise ValidationError("INVALID_DATA_BINDING")
        return
    if literals and set(value) == {"literal"}:
        literal = value["literal"]
        if type(literal) not in {str, int, bool}:
            raise ValidationError("INVALID_DATA_BINDING")
        if type(literal) is str and len(literal) > 2000:
            raise ValidationError("INVALID_DATA_BINDING")
        return
    raise ValidationError("INVALID_DATA_BINDING")


def _reject_unsafe_fields(value):
    if type(value) is dict:
        for key, child in value.items():
            if key in _FORBIDDEN_KEYS:
                raise ValidationError("UNSAFE_APPLICATION_FIELD")
            _reject_unsafe_fields(child)
    elif type(value) is list:
        for child in value:
            _reject_unsafe_fields(child)


def _components(definition):
    template = definition.get("surfaceTemplate")
    if type(template) is not dict:
        raise ValidationError("INVALID_SURFACE_TEMPLATE")
    _closed(
        template, {"surfaceKey", "rootId", "inputSchema", "components"}, "INVALID_SURFACE_TEMPLATE"
    )
    parse_identifier(template["surfaceKey"])
    validate_input_schema(template["inputSchema"])
    components = template.get("components")
    if type(components) is not list or not 1 <= len(components) <= 128:
        raise ValidationError("INVALID_COMPONENTS")
    by_id, events, names, binding_paths = {}, {}, set(), set()
    for item in components:
        if type(item) is not dict:
            raise ValidationError("INVALID_COMPONENT")
        component_id, component = item.get("id"), item.get("component")
        if (
            type(component_id) is not str
            or not component_id
            or component_id in by_id
            or component not in _ALLOWED_COMPONENTS
        ):
            raise ValidationError("INVALID_COMPONENT")
        by_id[component_id] = item
        names.add(component)
        if component == "Column":
            _closed(item, {"id", "component", "children"}, "INVALID_COMPONENT")
            if type(item["children"]) is not list:
                raise ValidationError("INVALID_COMPONENT")
        elif component == "Text":
            _closed(item, {"id", "component", "text"}, "INVALID_COMPONENT")
            _binding(item["text"])
            binding_paths.add(item["text"]["path"])
        elif component == "ChoicePicker":
            _closed(item, {"id", "component", "options", "value", "variant"}, "INVALID_COMPONENT")
            _binding(item["options"])
            _binding(item["value"])
            binding_paths.update((item["options"]["path"], item["value"]["path"]))
            if item["variant"] != "mutuallyExclusive":
                raise ValidationError("INVALID_COMPONENT")
        else:
            _closed(item, {"id", "component", "label", "action"}, "INVALID_COMPONENT")
            if type(item["label"]) is not str or not 1 <= len(item["label"]) <= 2000:
                raise ValidationError("INVALID_COMPONENT")
            _closed(item["action"], {"event"}, "INVALID_ACTION_EVENT")
            event = item["action"]["event"]
            _closed(event, {"name", "context"}, "INVALID_ACTION_EVENT")
            name = event["name"]
            if type(name) is not str or not name or name in events:
                raise ValidationError("INVALID_ACTION_EVENT")
            if type(event["context"]) is not dict or len(event["context"]) > 64:
                raise ValidationError("INVALID_ACTION_EVENT")
            for binding in event["context"].values():
                _binding(binding, literals=True)
                if "path" in binding:
                    binding_paths.add(binding["path"])
            events[name] = component_id
    root = template.get("rootId")
    if root not in by_id:
        raise ValidationError("INVALID_COMPONENT_GRAPH")
    visiting, visited = set(), set()

    def visit(component_id):
        if component_id in visiting:
            raise ValidationError("INVALID_COMPONENT_GRAPH")
        if component_id in visited:
            return
        visiting.add(component_id)
        for child_id in by_id[component_id].get("children", ()):
            if child_id not in by_id:
                raise ValidationError("INVALID_COMPONENT_GRAPH")
            visit(child_id)
        visiting.remove(component_id)
        visited.add(component_id)

    visit(root)
    if len(visited) != len(by_id):
        raise ValidationError("INVALID_COMPONENT_GRAPH")
    if any(not schema_path_exists(template["inputSchema"], path) for path in binding_paths):
        raise ValidationError("APPLICATION_BINDING_PATH_NOT_DECLARED")
    return events, frozenset(names)


def _definition_profile(key, definition):
    if type(definition) is not dict:
        raise ValidationError("INVALID_APPLICATION")
    _reject_unsafe_fields(definition)
    asset = definition.get("asset")
    _closed(
        asset,
        {"kind", "applicationKey", "protocolProfileRef", "componentCatalogRef"},
        "INVALID_APPLICATION_ASSET",
    )
    if asset["kind"] != "APPLICATION" or asset["applicationKey"] != key:
        raise ValidationError("APPLICATION_KEY_MISMATCH")
    for field in ("applicationKey", "protocolProfileRef", "componentCatalogRef"):
        parse_identifier(asset[field])
    render = definition.get("renderPolicy")
    _closed(render, {"tool", "interactionMode", "requiresPause"}, "INVALID_RENDER_POLICY")
    if render["tool"] != "render_application":
        raise ValidationError("INVALID_RENDER_POLICY")
    mode = render["interactionMode"]
    if mode == "DISPLAY_ONLY" and render["requiresPause"] is not False:
        raise ValidationError("DISPLAY_ONLY_MUST_NOT_WAIT")
    if mode == "INTERACTIVE" and render["requiresPause"] is not True:
        raise ValidationError("INTERACTIVE_MUST_WAIT")
    if mode not in {"DISPLAY_ONLY", "INTERACTIVE"}:
        raise ValidationError("INVALID_INTERACTION_MODE")
    if definition.get("versionAdmissionPolicy") != {
        "compareBeforeExecution": True,
        "compareBeforeContinue": True,
        "compareBeforeAction": True,
        "onMismatch": "RESET_REQUIRED",
    }:
        raise ValidationError("INVALID_VERSION_ADMISSION")
    if definition.get("finalizerPolicy") != {
        "mayOverrideBusinessFacts": False,
        "mayBypassRequiredInteraction": False,
    }:
        raise ValidationError("INVALID_FINALIZER_POLICY")
    retry = definition.get("retryPolicy")
    _closed(retry, {"allowedReasons"}, "INVALID_RETRY_POLICY")
    reasons = retry["allowedReasons"]
    if type(reasons) is not list or len(reasons) != len(set(reasons)):
        raise ValidationError("INVALID_RETRY_POLICY")
    interaction, actions = (definition.get("interactionPolicy"), definition.get("actionPolicies"))
    if type(actions) is not list:
        raise ValidationError("INVALID_ACTION_POLICIES")
    events, component_names = _components(definition)
    ability_releases = []
    if mode == "DISPLAY_ONLY":
        if interaction not in _DISPLAY_POLICIES:
            raise ValidationError("INVALID_DISPLAY_POLICY")
        if actions or events or not set(reasons) <= {"RENDER_FAILED"}:
            raise ValidationError("INVALID_DISPLAY_POLICY")
    else:
        if interaction != {
            "bindingScope": "RUNTIME_NODE_CARD_FORM",
            "ordinaryChatMayResume": False,
            "routeDirectlyWithoutAiReselection": True,
        }:
            raise ValidationError("INVALID_INTERACTION_POLICY")
        if not set(reasons) <= _INTERACTIVE_RETRY or not actions:
            raise ValidationError("INVALID_INTERACTION_POLICY")
        policies = {}
        required = {
            "actionName",
            "sourceComponentId",
            "abilityReleaseRef",
            "successPolicyRef",
            "completeInteractionOnSuccess",
            "controlRequestDedupeOnly",
            "businessIdempotencyOwner",
        }
        for policy in actions:
            _closed(policy, required, "INVALID_ACTION_POLICY")
            action_name = policy["actionName"]
            if (
                type(action_name) is not str
                or not action_name
                or action_name in policies
                or events.get(action_name) != policy["sourceComponentId"]
            ):
                raise ValidationError("INVALID_ACTION_POLICY")
            reference = policy["abilityReleaseRef"]
            if type(reference) is not str or reference.count("@") != 1:
                raise ValidationError("INVALID_ABILITY_RELEASE")
            ability_key, version = reference.split("@")
            parse_identifier(ability_key)
            parse_identifier(version)
            if version.lower() in _FLOATING_VERSIONS:
                raise ValidationError("FLOATING_ABILITY_RELEASE")
            if (
                type(policy["successPolicyRef"]) is not str
                or not policy["successPolicyRef"]
                or type(policy["completeInteractionOnSuccess"]) is not bool
                or policy["controlRequestDedupeOnly"] is not True
                or policy["businessIdempotencyOwner"] != "CALLED_API_BACKEND"
            ):
                raise ValidationError("INVALID_ACTION_POLICY")
            policies[action_name] = policy
            ability_releases.append((ability_key, version))
        if policies.keys() != events.keys():
            raise ValidationError("INVALID_ACTION_POLICY")
    return (asset["componentCatalogRef"], tuple(ability_releases), component_names)
