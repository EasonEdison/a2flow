"""Focused AF10 Ability management tests."""
from copy import deepcopy
import hashlib
import unittest

from a2flow_management import (
    ManagedDraft,
    ManagementError,
    ManagementService,
    MemoryDraftRepository,
    PublicationTarget,
    TrustedManagementContext,
)
from a2flow_management.contracts import canonical
from capability_registry import (
    AbilityDefinitionValidator,
    AdapterOperationDescriptor,
    SharedResultPolicySetValidator,
)
from capability_registry.management import create_ability_feature


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def ability_document():
    return {
        "abilityKey": "demo.catalog.lookup",
        "modelArgumentSchema": {
            "type": "object", "additionalProperties": False,
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        "resolvedInputSchema": {
            "type": "object", "additionalProperties": False,
            "required": ["query", "userId"],
            "properties": {
                "query": {"type": "string"},
                "userId": {"type": "string"},
            },
        },
        "outputSchema": {
            "type": "object", "additionalProperties": False,
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
        },
        "inputBindings": [
            {"targetPath": "/query", "source": "MODEL_ARGUMENT",
             "sourcePath": "/query"},
            {"targetPath": "/userId", "source": "TRUSTED_CONTEXT",
             "sourcePath": "/userId"},
        ],
        "credentialRequirements": [
            {"slotId": "demoRead", "required": True}],
        "adapterOperationRef": "demo.catalog.lookup.read",
        "resultInterpretationPolicies": [{
            "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
            "policyRef": "okTrue",
            "operator": "JSON_POINTER_EQUALS",
            "jsonPointer": "/ok",
            "expectedLiteral": True,
        }],
        "defaultSuccessPolicyRef": "okTrue",
    }


class OperationCatalog:
    def lookup(self, operation_ref):
        if operation_ref != "demo.catalog.lookup.read":
            return None
        return AdapterOperationDescriptor(
            operation_ref=operation_ref,
            input_paths=frozenset({"/query", "/userId"}),
            credential_slots=frozenset({"demoRead"}),
        )


class FakeAbilityReader:
    def __init__(self):
        definition = ability_document()
        value = {
            "kind": "ABILITY", "key": definition["abilityKey"],
            "assetId": "ability-demo", "versionId": "v1",
            "definition": definition, "dependencies": [],
        }
        self.published = {
            **value, "contentDigest": digest(value),
            "selection": "PRT_CURRENT",
        }

    def list_abilities(self, context):
        return ({
            "abilityKey": self.published["key"],
            "assetId": self.published["assetId"],
            "versionId": self.published["versionId"],
        },)

    def resolve_asset(self, kind, key, context):
        if kind == "ABILITY" and key == self.published["key"]:
            return self.published
        raise ManagementError("ASSET_NOT_FOUND", 404)


def feature(reader, drafts):
    validator = AbilityDefinitionValidator(
        OperationCatalog(), SharedResultPolicySetValidator())
    return create_ability_feature(reader, drafts, "a2flow-demo", validator)


ADMIN = TrustedManagementContext("admin-1", "PRT", frozenset({"ADMIN"}))
USER = TrustedManagementContext("user-1", "PRT", frozenset({"USER"}))


class AbilityManagementTests(unittest.TestCase):
    def setUp(self):
        self.reader = FakeAbilityReader()
        self.drafts = MemoryDraftRepository("PRT")
        self.service = ManagementService([feature(self.reader, self.drafts)])

    def test_user_can_browse_but_cannot_open_drafts(self):
        listed = self.service.list_published(USER, "ABILITY")
        self.assertEqual("demo.catalog.lookup", listed[0]["abilityKey"])
        detail = self.service.get_published(
            USER, "ABILITY", "demo.catalog.lookup")
        self.assertEqual("demo.catalog.lookup.read",
                         detail["definition"]["adapterOperationRef"])
        self.assertEqual("PRT_CURRENT", detail["resolution"]["selection"])
        with self.assertRaisesRegex(ManagementError, "ADMIN_REQUIRED"):
            self.service.get_draft(
                USER, "ABILITY", "demo.catalog.lookup")

    def test_admin_can_edit_and_validate_draft(self):
        initial = self.service.get_draft(
            ADMIN, "ABILITY", "demo.catalog.lookup")
        self.assertEqual(0, initial.revision)
        invalid = ability_document()
        invalid["outputSchema"] = []
        saved = self.service.save_draft(
            ADMIN, "ABILITY", "demo.catalog.lookup", 0, invalid)
        self.assertEqual(1, saved.revision)
        report = self.service.validate_draft(
            ADMIN, "ABILITY", "demo.catalog.lookup")
        self.assertFalse(report.valid)
        self.assertIn("ABILITY_SCHEMA_INVALID",
                      {issue["code"] for issue in report.issues})
        fixed = self.service.save_draft(
            ADMIN, "ABILITY", "demo.catalog.lookup", 1,
            ability_document())
        self.assertEqual(2, fixed.revision)
        self.assertTrue(self.service.validate_draft(
            ADMIN, "ABILITY", "demo.catalog.lookup").valid)

    def test_save_rejects_untrusted_operation_and_credential_material(self):
        unknown = ability_document()
        unknown["adapterOperationRef"] = "https://example.invalid/run"
        with self.assertRaisesRegex(ManagementError,
                                    "UNTRUSTED_ABILITY_REFERENCE"):
            self.service.save_draft(
                ADMIN, "ABILITY", "demo.catalog.lookup", 0, unknown)
        credential = ability_document()
        credential["credentialRequirements"][0]["token"] = "do-not-store"
        with self.assertRaisesRegex(ManagementError,
                                    "UNTRUSTED_ABILITY_REFERENCE"):
            self.service.save_draft(
                ADMIN, "ABILITY", "demo.catalog.lookup", 0, credential)
        credential = ability_document()
        credential["credentialRequirements"] = "literal-secret-value"
        with self.assertRaisesRegex(ManagementError,
                                    "UNTRUSTED_ABILITY_REFERENCE"):
            self.service.save_draft(
                ADMIN, "ABILITY", "demo.catalog.lookup", 0, credential)
        executable = ability_document()
        executable["script"] = "print('not allowed')"
        with self.assertRaisesRegex(ManagementError,
                                    "INVALID_ABILITY_DRAFT_FIELDS"):
            self.service.save_draft(
                ADMIN, "ABILITY", "demo.catalog.lookup", 0, executable)
        self.assertIsNone(self.drafts.get(
            "a2flow-demo", "ABILITY", "demo.catalog.lookup"))

    def test_publication_plan_is_validated_and_does_not_publish(self):
        self.service.save_draft(
            ADMIN, "ABILITY", "demo.catalog.lookup", 0,
            ability_document())
        plan = self.service.prepare_publication(
            ADMIN, "ABILITY", "demo.catalog.lookup", 1,
            PublicationTarget("PRT", "v2", "CURRENT"))
        self.assertEqual("ABILITY", plan.kind)
        self.assertEqual("v2", plan.candidate["versionId"])
        self.assertEqual("ability-demo", plan.candidate["assetId"])
        value = {key: value for key, value in plan.candidate.items()
                 if key != "contentDigest"}
        self.assertEqual(
            digest(value), plan.candidate["contentDigest"])
        self.assertEqual("v1", self.reader.published["versionId"])

    def test_publication_uses_one_draft_snapshot(self):
        first = ManagedDraft.create(
            "ABILITY", "demo.catalog.lookup", 1,
            ability_document(), "admin-1")
        moved_document = deepcopy(ability_document())
        moved_document["outputSchema"] = []
        second = ManagedDraft.create(
            "ABILITY", "demo.catalog.lookup", 2,
            moved_document, "admin-1")

        class MovingDrafts:
            environment = "PRT"

            def __init__(inner):
                inner.calls = 0

            def get(inner, namespace, kind, key):
                inner.calls += 1
                return first if inner.calls == 1 else second

            def save(inner, namespace, draft, expected_revision):
                raise AssertionError("prepare must not save")

        moving = MovingDrafts()
        service = ManagementService([feature(self.reader, moving)])
        plan = service.prepare_publication(
            ADMIN, "ABILITY", "demo.catalog.lookup", 1,
            PublicationTarget("PRT", "v2", "CURRENT"))
        self.assertEqual(1, plan.draft_revision)
        self.assertEqual(1, moving.calls)

    def test_wrong_environment_is_rejected_before_draft_io(self):
        class CountingDrafts:
            environment = "PRT"

            def __init__(inner):
                inner.calls = 0

            def get(inner, namespace, kind, key):
                inner.calls += 1
                raise AssertionError("must reject before get")

            def save(inner, namespace, draft, expected_revision):
                inner.calls += 1
                raise AssertionError("must reject before save")

        drafts = CountingDrafts()
        service = ManagementService([feature(self.reader, drafts)])
        online = TrustedManagementContext(
            "admin-1", "ONLINE", frozenset({"ADMIN"}))
        with self.assertRaisesRegex(ManagementError,
                                    "DRAFT_ENVIRONMENT_MISMATCH"):
            service.get_draft(
                online, "ABILITY", "demo.catalog.lookup")
        with self.assertRaisesRegex(ManagementError,
                                    "DRAFT_ENVIRONMENT_MISMATCH"):
            service.save_draft(
                online, "ABILITY", "demo.catalog.lookup", 0,
                ability_document())
        self.assertEqual(0, drafts.calls)


if __name__ == "__main__":
    unittest.main()
