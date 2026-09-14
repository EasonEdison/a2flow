"""Bounded APPLICATION management for the shared A2Flow management host.

The feature prepares immutable publication candidates but never writes asset
versions or serving state. Runtime compatibility remains owned by the
environment-bound asset validator injected through AssetReader.
"""

import hashlib

from a2flow_asset_store.records import canonical as asset_canonical, digest
from a2flow_management import (
    ManagedDraft,
    ManagementError,
    ManagementFeature,
    PublicationPlan,
    ValidationReport,
    require_admin,
)
from skillweave_contracts import TrustedContext, parse_identifier


_ALLOWED_COMPONENTS = frozenset({"Column", "Text", "ChoicePicker", "Button"})
_ALLOWED_DEPENDENCY_KINDS = frozenset({"ABILITY", "COMPONENT"})
_FLOATING_VERSIONS = frozenset({"default", "draft", "latest"})
_FORBIDDEN_KEYS = frozenset({
    "credential", "credentials", "environment", "grayTarget", "href", "html",
    "roles", "script", "src", "uri", "url", "userId",
})
_INTERACTIVE_RETRY = frozenset({
    "RENDER_FAILED", "ACTION_CALL_FAILED", "ACTION_RESULT_NOT_SUCCESS",
})


def _closed(value, keys, code):
    if type(value) is not dict or set(value) != set(keys):
        raise ManagementError(code)


def _binding(value, *, literals=False):
    if type(value) is not dict or len(value) != 1:
        raise ManagementError("INVALID_DATA_BINDING")
    if set(value) == {"path"}:
        path = value["path"]
        if type(path) is not str or not path.startswith("/") or len(path) > 256:
            raise ManagementError("INVALID_DATA_BINDING")
        return
    if literals and set(value) == {"literal"}:
        literal = value["literal"]
        if type(literal) not in {str, int, bool}:
            raise ManagementError("INVALID_DATA_BINDING")
        if type(literal) is str and len(literal) > 2000:
            raise ManagementError("INVALID_DATA_BINDING")
        return
    raise ManagementError("INVALID_DATA_BINDING")


def _reject_unsafe_fields(value):
    if type(value) is dict:
        for key, child in value.items():
            if key in _FORBIDDEN_KEYS:
                raise ManagementError("UNSAFE_APPLICATION_FIELD")
            _reject_unsafe_fields(child)
    elif type(value) is list:
        for child in value:
            _reject_unsafe_fields(child)


def _components(definition):
    template = definition.get("surfaceTemplate")
    if type(template) is not dict:
        raise ManagementError("INVALID_SURFACE_TEMPLATE")
    components = template.get("components")
    if type(components) is not list or not 1 <= len(components) <= 128:
        raise ManagementError("INVALID_COMPONENTS")
    by_id, events = {}, {}
    for item in components:
        if type(item) is not dict:
            raise ManagementError("INVALID_COMPONENT")
        component_id, component = item.get("id"), item.get("component")
        if (type(component_id) is not str or not component_id
                or component_id in by_id or component not in _ALLOWED_COMPONENTS):
            raise ManagementError("INVALID_COMPONENT")
        by_id[component_id] = item
        if component == "Column":
            _closed(item, {"id", "component", "children"}, "INVALID_COMPONENT")
            if type(item["children"]) is not list:
                raise ManagementError("INVALID_COMPONENT")
        elif component == "Text":
            _closed(item, {"id", "component", "text"}, "INVALID_COMPONENT")
            _binding(item["text"])
        elif component == "ChoicePicker":
            _closed(item, {"id", "component", "options", "value", "variant"},
                    "INVALID_COMPONENT")
            _binding(item["options"])
            _binding(item["value"])
            if item["variant"] != "mutuallyExclusive":
                raise ManagementError("INVALID_COMPONENT")
        else:
            _closed(item, {"id", "component", "label", "action"},
                    "INVALID_COMPONENT")
            if type(item["label"]) is not str or not 1 <= len(item["label"]) <= 2000:
                raise ManagementError("INVALID_COMPONENT")
            _closed(item["action"], {"event"}, "INVALID_ACTION_EVENT")
            event = item["action"]["event"]
            _closed(event, {"name", "context"}, "INVALID_ACTION_EVENT")
            name = event["name"]
            if type(name) is not str or not name or name in events:
                raise ManagementError("INVALID_ACTION_EVENT")
            if type(event["context"]) is not dict or len(event["context"]) > 64:
                raise ManagementError("INVALID_ACTION_EVENT")
            for binding in event["context"].values():
                _binding(binding, literals=True)
            events[name] = component_id
    root = template.get("rootId")
    if root not in by_id:
        raise ManagementError("INVALID_COMPONENT_GRAPH")
    visiting, visited = set(), set()

    def visit(component_id):
        if component_id in visiting:
            raise ManagementError("INVALID_COMPONENT_GRAPH")
        if component_id in visited:
            return
        visiting.add(component_id)
        for child_id in by_id[component_id].get("children", ()):
            if child_id not in by_id:
                raise ManagementError("INVALID_COMPONENT_GRAPH")
            visit(child_id)
        visiting.remove(component_id)
        visited.add(component_id)

    visit(root)
    if len(visited) != len(by_id):
        raise ManagementError("INVALID_COMPONENT_GRAPH")
    return events


def _definition_profile(key, definition):
    if type(definition) is not dict:
        raise ManagementError("INVALID_APPLICATION")
    _reject_unsafe_fields(definition)
    asset = definition.get("asset")
    _closed(asset, {"kind", "applicationKey", "protocolProfileRef",
                    "componentCatalogRef"}, "INVALID_APPLICATION_ASSET")
    if asset["kind"] != "APPLICATION" or asset["applicationKey"] != key:
        raise ManagementError("APPLICATION_KEY_MISMATCH")
    for field in ("applicationKey", "protocolProfileRef", "componentCatalogRef"):
        parse_identifier(asset[field])
    render = definition.get("renderPolicy")
    _closed(render, {"tool", "interactionMode", "requiresPause"},
            "INVALID_RENDER_POLICY")
    if render["tool"] != "render_application":
        raise ManagementError("INVALID_RENDER_POLICY")
    mode = render["interactionMode"]
    if mode == "DISPLAY_ONLY" and render["requiresPause"] is not False:
        raise ManagementError("DISPLAY_ONLY_MUST_NOT_WAIT")
    if mode == "INTERACTIVE" and render["requiresPause"] is not True:
        raise ManagementError("INTERACTIVE_MUST_WAIT")
    if mode not in {"DISPLAY_ONLY", "INTERACTIVE"}:
        raise ManagementError("INVALID_INTERACTION_MODE")
    if definition.get("versionAdmissionPolicy") != {
        "compareBeforeExecution": True, "compareBeforeContinue": True,
        "compareBeforeAction": True, "onMismatch": "RESET_REQUIRED",
    }:
        raise ManagementError("INVALID_VERSION_ADMISSION")
    if definition.get("finalizerPolicy") != {
        "mayOverrideBusinessFacts": False,
        "mayBypassRequiredInteraction": False,
    }:
        raise ManagementError("INVALID_FINALIZER_POLICY")
    retry = definition.get("retryPolicy")
    _closed(retry, {"allowedReasons"}, "INVALID_RETRY_POLICY")
    reasons = retry["allowedReasons"]
    if type(reasons) is not list or len(reasons) != len(set(reasons)):
        raise ManagementError("INVALID_RETRY_POLICY")
    interaction, actions = (
        definition.get("interactionPolicy"), definition.get("actionPolicies"))
    if type(actions) is not list:
        raise ManagementError("INVALID_ACTION_POLICIES")
    events = _components(definition)
    ability_releases = []
    if mode == "DISPLAY_ONLY":
        if interaction != {"bindingScope": "NONE", "ordinaryChatMayResume": False}:
            raise ManagementError("INVALID_DISPLAY_POLICY")
        if actions or events or reasons != ["RENDER_FAILED"]:
            raise ManagementError("INVALID_DISPLAY_POLICY")
    else:
        if interaction != {
            "bindingScope": "RUNTIME_NODE_CARD_FORM",
            "ordinaryChatMayResume": False,
            "routeDirectlyWithoutAiReselection": True,
        }:
            raise ManagementError("INVALID_INTERACTION_POLICY")
        if frozenset(reasons) != _INTERACTIVE_RETRY or not actions:
            raise ManagementError("INVALID_INTERACTION_POLICY")
        policies = {}
        required = {"actionName", "sourceComponentId", "abilityReleaseRef",
                    "successPolicyRef", "completeInteractionOnSuccess",
                    "controlRequestDedupeOnly", "businessIdempotencyOwner"}
        for policy in actions:
            _closed(policy, required, "INVALID_ACTION_POLICY")
            action_name = policy["actionName"]
            if (type(action_name) is not str or not action_name
                    or action_name in policies
                    or events.get(action_name) != policy["sourceComponentId"]):
                raise ManagementError("INVALID_ACTION_POLICY")
            reference = policy["abilityReleaseRef"]
            if type(reference) is not str or reference.count("@") != 1:
                raise ManagementError("INVALID_ABILITY_RELEASE")
            ability_key, version = reference.split("@")
            parse_identifier(ability_key)
            parse_identifier(version)
            if version.lower() in _FLOATING_VERSIONS:
                raise ManagementError("FLOATING_ABILITY_RELEASE")
            if (type(policy["successPolicyRef"]) is not str
                    or not policy["successPolicyRef"]
                    or type(policy["completeInteractionOnSuccess"]) is not bool
                    or policy["controlRequestDedupeOnly"] is not True
                    or policy["businessIdempotencyOwner"] != "CALLED_API_BACKEND"):
                raise ManagementError("INVALID_ACTION_POLICY")
            policies[action_name] = policy
            ability_releases.append((ability_key, version))
        if policies.keys() != events.keys():
            raise ManagementError("INVALID_ACTION_POLICY")
    return asset["componentCatalogRef"], tuple(ability_releases)


class ApplicationManagementFeature(ManagementFeature):
    """APPLICATION adapter with backend-authoritative validation and no publish."""

    kind = "APPLICATION"

    def __init__(self, reader, drafts, namespace):
        self.reader, self.drafts, self.namespace = reader, drafts, namespace

    @staticmethod
    def _runtime_context(context):
        return TrustedContext(context.user_id, context.environment)

    def _draft_context(self, context):
        require_admin(context)
        if context.environment != self.drafts.environment:
            raise ManagementError("DRAFT_ENVIRONMENT_MISMATCH", 403)

    def list_published(self, context):
        return tuple(self.reader.list_assets(
            self.kind, self._runtime_context(context)))

    def get_published(self, context, key):
        parse_identifier(key)
        return self.reader.resolve_asset(
            self.kind, key, self._runtime_context(context))

    def _draft_snapshot(self, context, key):
        parse_identifier(key)
        self._draft_context(context)
        draft = self.drafts.get(self.namespace, self.kind, key)
        if draft is not None:
            return draft
        published = self.get_published(context, key)
        return ManagedDraft.create(
            self.kind, key, 0, {
                "definition": published["definition"],
                "dependencies": published["dependencies"],
            }, context.user_id)

    def get_draft(self, context, key):
        return self._draft_snapshot(context, key)

    def save_draft(self, context, key, expected_revision, document):
        parse_identifier(key)
        self._draft_context(context)
        candidate = ManagedDraft.create(
            self.kind, key, 0, document, context.user_id)
        return self.drafts.save(self.namespace, candidate, expected_revision)

    def _validate_snapshot(self, draft, context):
        try:
            _closed(draft.document, {"definition", "dependencies"},
                    "INVALID_DRAFT_FIELDS")
            definition = draft.document["definition"]
            component_key, abilities = _definition_profile(draft.key, definition)
            dependencies = draft.document["dependencies"]
            if type(dependencies) is not list or len(dependencies) > 128:
                raise ManagementError("INVALID_DEPENDENCIES")
            identities = []
            for dependency in dependencies:
                _closed(dependency, {"kind", "key"}, "INVALID_DEPENDENCIES")
                if dependency["kind"] not in _ALLOWED_DEPENDENCY_KINDS:
                    raise ManagementError("INVALID_DEPENDENCIES")
                parse_identifier(dependency["key"])
                identities.append((dependency["kind"], dependency["key"]))
            expected = {("COMPONENT", component_key)}
            expected.update(("ABILITY", key) for key, _ in abilities)
            if len(identities) != len(set(identities)) or set(identities) != expected:
                raise ManagementError("APPLICATION_DEPENDENCY_MISMATCH")
            runtime = self._runtime_context(context)
            self.reader.resolve_asset("COMPONENT", component_key, runtime)
            for ability_key, expected_version in abilities:
                resolved = self.reader.resolve_asset("ABILITY", ability_key, runtime)
                if resolved["versionId"] != expected_version:
                    raise ManagementError("APPLICATION_BINDING_VERSION_MISMATCH")
            self.reader.repository.validator.validate_definition(
                self.kind, draft.key, definition)
        except ManagementError as error:
            return ValidationReport.failure(error.code)
        except Exception as error:
            return ValidationReport.failure(
                getattr(error, "code", "INVALID_APPLICATION"))
        return ValidationReport.success({
            "definition": definition, "dependencies": dependencies})

    def validate_draft(self, context, key):
        draft = self._draft_snapshot(context, key)
        return self._validate_snapshot(draft, context)

    def prepare_publication(self, context, key, expected_revision, target):
        parse_identifier(key)
        self._draft_context(context)
        if target.environment != context.environment:
            raise ManagementError("TARGET_ENVIRONMENT_MISMATCH")
        draft = self.drafts.get(self.namespace, self.kind, key)
        if draft is None:
            published = self.get_published(context, key)
            draft = ManagedDraft.create(
                self.kind, key, 0, {
                    "definition": published["definition"],
                    "dependencies": published["dependencies"],
                }, context.user_id)
        if draft.revision != expected_revision:
            raise ManagementError("DRAFT_REVISION_CONFLICT", 409)
        report = self._validate_snapshot(draft, context)
        if not report.valid:
            raise ManagementError("DRAFT_NOT_PUBLISHABLE", 409)
        normalized = report.normalized
        asset_id = "application-" + hashlib.sha256(
            key.encode()).hexdigest()[:24]
        try:
            asset_id = self.reader.resolve_asset(
                self.kind, key, self._runtime_context(context))["assetId"]
        except Exception as error:
            if getattr(error, "code", None) != "ASSET_NOT_FOUND":
                raise
        value = {
            "kind": self.kind, "key": key, "assetId": asset_id,
            "versionId": target.version_id,
            "definition": normalized["definition"],
            "dependencies": normalized["dependencies"],
        }
        candidate = {**value, "contentDigest": digest(asset_canonical(value))}
        return PublicationPlan.create(
            self.kind, key, draft.revision, target, candidate)


def create_application_feature(reader, drafts, namespace):
    """Bind to explicit environment-local reader and draft ports."""
    return ApplicationManagementFeature(reader, drafts, namespace)
