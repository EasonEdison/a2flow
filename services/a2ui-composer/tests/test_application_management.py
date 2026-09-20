"""Focused AF10 APPLICATION management compatibility tests."""

import copy
from types import SimpleNamespace
import unittest

from a2flow_management import (
    ManagementError,
    ManagementService,
    PublicationTarget,
    TrustedManagementContext,
)
from a2flow_asset_store import AssetReader
from a2ui_composer import application_validator, create_application_feature
from activity_planning_demo import bundle_validator, component_definition
from activity_planning_demo.bundle import NAMESPACE, make_bundle


APPLICATION_KEY = "activity-planning.confirm"
COMPONENT_KEY = "activity-planning.basic"
ABILITY_KEY = "activity-planning.confirm"


def interactive_definition():
    return {
        "asset": {"kind": "APPLICATION", "applicationKey": APPLICATION_KEY,
                  "protocolProfileRef": "a2flow.mvp08.v1",
                  "componentCatalogRef": COMPONENT_KEY},
        "renderPolicy": {"tool": "render_application",
                         "interactionMode": "INTERACTIVE",
                         "requiresPause": True},
        "interactionPolicy": {"bindingScope": "RUNTIME_NODE_CARD_FORM",
                              "ordinaryChatMayResume": False,
                              "routeDirectlyWithoutAiReselection": True},
        "versionAdmissionPolicy": {"compareBeforeExecution": True,
                                   "compareBeforeContinue": True,
                                   "compareBeforeAction": True,
                                   "onMismatch": "RESET_REQUIRED"},
        "actionPolicies": [{
            "actionName": "confirm_activity", "sourceComponentId": "confirm",
            "abilityReleaseRef": ABILITY_KEY + "@v1",
            "successPolicyRef": "confirmed",
            "completeInteractionOnSuccess": True,
            "controlRequestDedupeOnly": True,
            "businessIdempotencyOwner": "CALLED_API_BACKEND"}],
        "retryPolicy": {"allowedReasons": [
            "RENDER_FAILED", "ACTION_CALL_FAILED", "ACTION_RESULT_NOT_SUCCESS"]},
        "finalizerPolicy": {"mayOverrideBusinessFacts": False,
                            "mayBypassRequiredInteraction": False},
        "surfaceTemplate": {
            "surfaceKey": "activity_selection", "rootId": "root",
            "inputSchema": {"type": "object", "required": ["prompt", "options"],
                            "additionalProperties": False,
                            "properties": {"prompt": {"type": "string"},
                                           "options": {
                                               "type": "array",
                                               "items": {"type": "string"}},
                                           "optionId": {"type": "string"}}},
            "components": [
                {"id": "root", "component": "Column",
                 "children": ["prompt", "selection", "confirm"]},
                {"id": "prompt", "component": "Text",
                 "text": {"path": "/prompt"}},
                {"id": "selection", "component": "ChoicePicker",
                 "options": {"path": "/options"}, "value": {"path": "/optionId"},
                 "variant": "mutuallyExclusive"},
                {"id": "confirm", "component": "Button", "label": "Confirm",
                 "action": {"event": {"name": "confirm_activity",
                                      "context": {
                                          "optionId": {"path": "/optionId"},
                                          "confirmed": {"literal": True}}}}}],
        },
    }


def display_definition():
    value = interactive_definition()
    value["renderPolicy"] = {"tool": "render_application",
                             "interactionMode": "DISPLAY_ONLY",
                             "requiresPause": False}
    value["interactionPolicy"] = {"bindingScope": "NONE",
                                  "ordinaryChatMayResume": False}
    value["actionPolicies"] = []
    value["retryPolicy"] = {"allowedReasons": ["RENDER_FAILED"]}
    value["surfaceTemplate"]["components"] = [
        {"id": "root", "component": "Column", "children": ["prompt"]},
        {"id": "prompt", "component": "Text", "text": {"path": "/prompt"}}]
    return value


class Validator:
    def validate_definition(self, kind, key, definition):
        if kind != "APPLICATION" or application_validator(definition) is not True:
            raise ManagementError("INVALID_APPLICATION")


class Reader:
    def __init__(self, definition):
        self.definition = copy.deepcopy(definition)
        self.repository = SimpleNamespace(
            environment="PRT", validator=Validator())
        self.published_version = "v1"

    def list_assets(self, kind, context):
        return ({"kind": kind, "key": APPLICATION_KEY,
                 "assetId": "application-confirm",
                 "versionId": self.published_version,
                 "contentDigest": "sha256:" + "1" * 64,
                 "selection": "PRT_CURRENT"},)

    def asset_exists(self, kind, key, context):
        return kind == "APPLICATION" and key == APPLICATION_KEY

    def resolve_asset(self, kind, key, context):
        if kind == "APPLICATION" and key == APPLICATION_KEY:
            return {"kind": kind, "key": key, "assetId": "application-confirm",
                    "versionId": self.published_version,
                    "contentDigest": "sha256:" + "1" * 64,
                    "definition": copy.deepcopy(self.definition),
                    "dependencies": [
                        {"kind": "COMPONENT", "key": COMPONENT_KEY},
                        *([{"kind": "ABILITY", "key": ABILITY_KEY}]
                          if self.definition["actionPolicies"] else [])],
                    "selection": "PRT_CURRENT"}
        if kind == "COMPONENT" and key == COMPONENT_KEY:
            return {"kind": kind, "key": key, "versionId": "v1",
                    "definition": component_definition()}
        if kind == "ABILITY" and key == ABILITY_KEY:
            return {"kind": kind, "key": key, "versionId": "v1"}
        raise ManagementError("ASSET_NOT_FOUND", 404)


class Drafts:
    environment = "PRT"

    def __init__(self):
        self.rows, self.get_calls, self.save_calls = {}, 0, 0

    def get(self, namespace, kind, key):
        self.get_calls += 1
        return self.rows.get((namespace, kind, key))

    def list(self, namespace, kind):
        return tuple(value for identity, value in sorted(self.rows.items())
                     if identity[:2] == (namespace, kind))

    def create(self, namespace, draft):
        return self.save(namespace, draft, 0)

    def save(self, namespace, draft, expected_revision):
        self.save_calls += 1
        identity = namespace, draft.kind, draft.key
        current = self.rows.get(identity)
        actual = 0 if current is None else current.revision
        if actual != expected_revision:
            raise ManagementError("DRAFT_REVISION_CONFLICT", 409)
        saved = type(draft).create(
            draft.kind, draft.key, actual + 1, draft.document, draft.updated_by)
        self.rows[identity] = saved
        return saved


class BundleRepository:
    environment = "PRT"

    def __init__(self):
        self.validator = bundle_validator()
        self.bundle = self.validator.validate(
            make_bundle("PRT"),
            expected_namespace=NAMESPACE,
            expected_environment="PRT",
        )

    def read(self, namespace):
        if namespace != NAMESPACE:
            raise AssertionError("unexpected namespace")
        return self.bundle


class ApplicationManagementTests(unittest.TestCase):
    def setUp(self):
        self.reader, self.drafts = Reader(interactive_definition()), Drafts()
        self.service = ManagementService([create_application_feature(
            self.reader, self.drafts, "a2flow-mvp-activity-planning")])
        self.admin = TrustedManagementContext(
            101, "PRT", frozenset({"ADMIN"}))
        self.user = TrustedManagementContext(
            102, "PRT", frozenset({"USER"}))

    @staticmethod
    def document(definition=None):
        value = interactive_definition() if definition is None else definition
        dependencies = [{"kind": "COMPONENT", "key": COMPONENT_KEY}]
        if value["actionPolicies"]:
            dependencies.append({"kind": "ABILITY", "key": ABILITY_KEY})
        return {"definition": value, "dependencies": dependencies}

    def test_user_browses_published_but_cannot_open_draft(self):
        listed = self.service.list_published(self.user, "APPLICATION")
        self.assertEqual(APPLICATION_KEY, listed[0]["key"])
        detail = self.service.get_published(
            self.user, "APPLICATION", APPLICATION_KEY)
        self.assertEqual("PRT_CURRENT", detail["selection"])
        with self.assertRaisesRegex(ManagementError, "ADMIN_REQUIRED"):
            self.service.get_draft(self.user, "APPLICATION", APPLICATION_KEY)

    def test_admin_creates_unconfigured_application_draft(self):
        created = self.service.create_draft(
            self.admin, "APPLICATION", "new.application")
        self.assertEqual("new.application",
                         created.document["definition"]["asset"]["applicationKey"])
        self.assertEqual("DISPLAY_ONLY",
                         created.document["definition"]["renderPolicy"]["interactionMode"])
        self.assertFalse(self.service.validate_draft(
            self.admin, "APPLICATION", "new.application").valid)
        self.assertIn("new.application", {
            item["key"] for item in self.service.list_published(
                self.admin, "APPLICATION")})
        self.assertNotIn("new.application", {
            item["key"] for item in self.service.list_published(
                self.user, "APPLICATION")})

    def test_interactive_validates_and_prepares_without_publish(self):
        saved = self.service.save_draft(
            self.admin, "APPLICATION", APPLICATION_KEY, 0, self.document())
        self.assertTrue(self.service.validate_draft(
            self.admin, "APPLICATION", APPLICATION_KEY).valid)
        plan = self.service.prepare_publication(
            self.admin, "APPLICATION", APPLICATION_KEY, saved.revision,
            PublicationTarget("PRT", "v2", "CURRENT"))
        policy = plan.candidate["definition"]["actionPolicies"][0]
        self.assertEqual("confirm_activity", policy["actionName"])
        self.assertTrue(policy["completeInteractionOnSuccess"])
        self.assertEqual("v1", self.reader.published_version)

    def test_changed_button_label_compiles_against_registered_catalog(self):
        definition = interactive_definition()
        definition["surfaceTemplate"]["components"][-1]["label"] = "Save selection"
        self.service.save_draft(
            self.admin, "APPLICATION", APPLICATION_KEY, 0,
            self.document(definition))
        self.assertTrue(self.service.validate_draft(
            self.admin, "APPLICATION", APPLICATION_KEY).valid)

    def test_unregistered_component_fails_closed(self):
        reader = Reader(interactive_definition())
        original_resolve = reader.resolve_asset

        def resolve(kind, key, context):
            result = original_resolve(kind, key, context)
            if kind == "COMPONENT":
                result["definition"]["components"].remove("Button")
            return result

        reader.resolve_asset = resolve
        service = ManagementService([create_application_feature(
            reader, Drafts(), "a2flow-mvp-activity-planning")])
        service.save_draft(
            self.admin, "APPLICATION", APPLICATION_KEY, 0,
            self.document())
        report = service.validate_draft(
            self.admin, "APPLICATION", APPLICATION_KEY)
        self.assertFalse(report.valid)
        self.assertEqual(
            "APPLICATION_COMPONENT_NOT_REGISTERED",
            report.issues[0]["code"])

    def test_application_and_catalog_protocol_must_match(self):
        value = interactive_definition()
        value["asset"]["protocolProfileRef"] = "a2flow.other.v1"
        self.service.save_draft(
            self.admin, "APPLICATION", APPLICATION_KEY, 0,
            self.document(value))
        report = self.service.validate_draft(
            self.admin, "APPLICATION", APPLICATION_KEY)
        self.assertFalse(report.valid)
        self.assertEqual(
            "APPLICATION_COMPONENT_PROTOCOL_MISMATCH",
            report.issues[0]["code"])

    def test_malformed_schema_types_return_bounded_validation_issue(self):
        mutations = (
            lambda schema: schema.__setitem__("type", []),
            lambda schema: schema.__setitem__("required", [{}]),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                service = ManagementService([create_application_feature(
                    Reader(interactive_definition()), Drafts(),
                    "a2flow-mvp-activity-planning")])
                value = interactive_definition()
                mutate(value["surfaceTemplate"]["inputSchema"])
                service.save_draft(
                    self.admin, "APPLICATION", APPLICATION_KEY, 0,
                    self.document(value))
                report = service.validate_draft(
                    self.admin, "APPLICATION", APPLICATION_KEY)
                self.assertFalse(report.valid)
                self.assertEqual(
                    "INVALID_APPLICATION_INPUT_SCHEMA",
                    report.issues[0]["code"])

    def test_display_only_never_waits_and_has_no_action(self):
        definition = display_definition()
        self.reader.definition = definition
        saved = self.service.save_draft(
            self.admin, "APPLICATION", APPLICATION_KEY, 0,
            self.document(definition))
        plan = self.service.prepare_publication(
            self.admin, "APPLICATION", APPLICATION_KEY, saved.revision,
            PublicationTarget("PRT", "display-v2", "CURRENT"))
        self.assertFalse(
            plan.candidate["definition"]["renderPolicy"]["requiresPause"])
        self.assertEqual([], plan.candidate["definition"]["actionPolicies"])

    def test_unsafe_fields_are_rejected_before_draft_save_io(self):
        for field, value in (
                ("credential", "secret"),
                ("script", "alert(1)"),
                ("userId", "forged-user"),
                ("roles", ["ADMIN"])):
            unsafe = self.document()
            unsafe["definition"]["surfaceTemplate"][field] = value
            before = self.drafts.save_calls
            with self.subTest(field=field), self.assertRaisesRegex(
                    ManagementError, "UNSAFE_APPLICATION_FIELD"):
                self.service.save_draft(
                    self.admin, "APPLICATION", APPLICATION_KEY, 0, unsafe)
            self.assertEqual(before, self.drafts.save_calls)

    def test_incomplete_safe_draft_can_be_saved_then_fails_validation(self):
        incomplete = {
            "definition": {
                "asset": {
                    "kind": "APPLICATION",
                    "applicationKey": APPLICATION_KEY,
                },
            },
            "dependencies": [],
        }
        saved = self.service.save_draft(
            self.admin, "APPLICATION", APPLICATION_KEY, 0, incomplete)
        self.assertEqual(1, saved.revision)
        report = self.service.validate_draft(
            self.admin, "APPLICATION", APPLICATION_KEY)
        self.assertFalse(report.valid)
        with self.assertRaisesRegex(ManagementError, "DRAFT_NOT_PUBLISHABLE"):
            self.service.prepare_publication(
                self.admin, "APPLICATION", APPLICATION_KEY, 1,
                PublicationTarget("PRT", "v2", "CURRENT"))

    def test_wrong_environment_rejects_before_draft_io(self):
        online = TrustedManagementContext(
            101, "ONLINE", frozenset({"ADMIN"}))
        operations = (
            lambda: self.service.get_draft(
                online, "APPLICATION", APPLICATION_KEY),
            lambda: self.service.save_draft(
                online, "APPLICATION", APPLICATION_KEY, 0, self.document()),
            lambda: self.service.validate_draft(
                online, "APPLICATION", APPLICATION_KEY),
            lambda: self.service.prepare_publication(
                online, "APPLICATION", APPLICATION_KEY, 0,
                PublicationTarget("ONLINE", "v2", "STABLE")),
        )
        for operation in operations:
            before = self.drafts.get_calls + self.drafts.save_calls
            with self.subTest(operation=operation), self.assertRaisesRegex(
                    ManagementError, "DRAFT_ENVIRONMENT_MISMATCH"):
                operation()
            self.assertEqual(
                before, self.drafts.get_calls + self.drafts.save_calls)

    def test_prepare_uses_one_immutable_draft_snapshot(self):
        saved = self.service.save_draft(
            self.admin, "APPLICATION", APPLICATION_KEY, 0, self.document())
        before = self.drafts.get_calls
        plan = self.service.prepare_publication(
            self.admin, "APPLICATION", APPLICATION_KEY, saved.revision,
            PublicationTarget("PRT", "v2", "CURRENT"))
        self.assertEqual(before + 1, self.drafts.get_calls)
        self.assertEqual(saved.document["definition"],
                         plan.candidate["definition"])

    def test_real_asset_reader_and_registered_validator_are_compatible(self):
        reader = AssetReader(BundleRepository(), NAMESPACE)
        service = ManagementService([
            create_application_feature(reader, Drafts(), NAMESPACE)])
        listed = service.list_published(self.user, "APPLICATION")
        self.assertIn(APPLICATION_KEY, {item["key"] for item in listed})
        detail = service.get_published(
            self.user, "APPLICATION", APPLICATION_KEY)
        draft = service.get_draft(
            self.admin, "APPLICATION", APPLICATION_KEY)
        report = service.validate_draft(
            self.admin, "APPLICATION", APPLICATION_KEY)
        plan = service.prepare_publication(
            self.admin, "APPLICATION", APPLICATION_KEY, 0,
            PublicationTarget("PRT", "compat-v2", "CURRENT"))
        self.assertEqual(detail["definition"], draft.document["definition"])
        self.assertTrue(report.valid)
        self.assertEqual("compat-v2", plan.candidate["versionId"])


if __name__ == "__main__":
    unittest.main()
