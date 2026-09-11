"""Offline source tests; SQL doubles are not PostgreSQL integration evidence."""
from contextlib import contextmanager
from copy import deepcopy
import unittest

from a2flow_asset_store import AssetError, AssetReader, PostgresAssetRepository
from a2flow_asset_store.records import canonical, digest
from activity_planning_demo import (
    bundle_validator, budget_activity, select_activity, MODEL_ABILITY_KEYS, CONFIRM_KEY,
)
from activity_planning_demo.bundle import make_bundle, NAMESPACE
from skillweave_contracts import TrustedContext
from skill_registry import (
    TrustedContext as RegistryContext, TrustedInvocationContext, InvocationScope,
    UseSkillRequest, use_skill,
)


class Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)
    def fetchone(self):
        return self.rows[0] if self.rows else None
    def fetchall(self):
        return self.rows


class DatabaseDouble:
    """Minimal recording SQL protocol double with transaction rollback."""
    def __init__(self):
        self.assets, self.states, self.calls = {}, {}, []
        self.env, self.database = "PRT", "asset_prt"
        self.connects, self.fail_insert = 0, False
    def connect(self, *args, **kwargs):
        self.connects += 1
        return self
    def close(self):
        pass
    @contextmanager
    def transaction(self):
        assets, states = deepcopy(self.assets), deepcopy(self.states)
        try:
            yield
        except Exception:
            self.assets, self.states = assets, states
            raise
    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if sql == "SELECT current_database()":
            return Rows([(self.database,)])
        if sql.startswith("SELECT environment"):
            return Rows([(self.env,)])
        if sql.startswith("SELECT count"):
            source = self.assets if "a2flow_asset_versions" in sql else self.states
            rows = [v for k, v in source.items() if k[0] == params[0]]
            return Rows([(len(rows), sum(len(v[0]) if isinstance(v, tuple) else len(v) for v in rows))])
        if sql.startswith("SELECT kind,asset_key,version_id"):
            return Rows([(*k[1:], v[0], v[1]) for k, v in sorted(self.assets.items()) if k[0] == params[0]])
        if sql.startswith("SELECT kind,asset_key,document"):
            return Rows([(*k[1:], v) for k, v in sorted(self.states.items()) if k[0] == params[0]])
        if sql.startswith("INSERT INTO a2flow_asset_versions"):
            if self.fail_insert:
                raise RuntimeError("database detail must not escape")
            self.assets[tuple(params[:4])] = (params[4], params[5])
        elif sql.startswith("INSERT INTO a2flow_asset_serving"):
            self.states[tuple(params[:3])] = params[3]
        elif not sql.startswith(("SET TRANSACTION", "SELECT pg_advisory")):
            raise AssertionError("unexpected SQL " + sql)
        return Rows()


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseDouble()
        self.validator = bundle_validator()
        self.repo = PostgresAssetRepository("not-a-real-dsn", environment="PRT",
            database="asset_prt", validator=self.validator, connection_factory=self.db.connect)
        self.document = make_bundle("PRT")

    def validate(self, doc):
        return self.validator.validate(doc, expected_namespace=NAMESPACE,
                                       expected_environment=doc["environment"])

    def resign(self, doc):
        for asset in doc["assets"]:
            asset["contentDigest"] = digest(canonical(
                {k: v for k, v in asset.items() if k != "contentDigest"}))
        return doc

    def test_seed_has_all_five_kinds_and_seven_assets(self):
        for env in ("PRT", "ONLINE"):
            result = self.validate(make_bundle(env))
            self.assertEqual(7, len(result.assets))
            self.assertEqual({"WORKFLOW", "SKILL", "APPLICATION", "COMPONENT", "ABILITY"},
                             {a.kind for a in result.assets})

    def test_dry_run_has_no_ddl_dml(self):
        self.assertEqual("WOULD_INSERT", self.repo.import_bundle(
            self.document, expected_namespace=NAMESPACE)["status"])
        self.assertEqual({}, self.db.assets)
        self.assertFalse(any(sql.startswith(("INSERT", "UPDATE", "DELETE", "CREATE"))
                             for sql, _ in self.db.calls))

    def test_import_then_noop_does_not_rewrite(self):
        self.assertEqual("INSERTED", self.repo.import_bundle(
            self.document, expected_namespace=NAMESPACE, dry_run=False)["status"])
        self.db.calls.clear()
        self.assertEqual("NO_CHANGE", self.repo.import_bundle(
            self.document, expected_namespace=NAMESPACE, dry_run=False)["status"])
        self.assertFalse(any(sql.startswith("INSERT") for sql, _ in self.db.calls))
        self.assertEqual(7, len(self.repo.read(NAMESPACE).assets))

    def test_conflict_does_not_overwrite_any_rows(self):
        self.repo.import_bundle(self.document, expected_namespace=NAMESPACE, dry_run=False)
        before = deepcopy(self.db.assets)
        changed = deepcopy(self.document)
        skill = next(a for a in changed["assets"] if a["kind"] == "SKILL")
        skill["definition"]["requiredToolNames"].append("another_hint")
        with self.assertRaisesRegex(AssetError, "ASSET_CONFLICT"):
            self.repo.import_bundle(self.resign(changed), expected_namespace=NAMESPACE, dry_run=False)
        self.assertEqual(before, self.db.assets)

    def test_failure_rolls_back_and_sanitizes_error(self):
        self.db.fail_insert = True
        with self.assertRaisesRegex(AssetError, "^ASSET_DATABASE_ERROR$"):
            self.repo.import_bundle(self.document, expected_namespace=NAMESPACE, dry_run=False)
        self.assertEqual({}, self.db.assets)
        self.assertEqual({}, self.db.states)

    def test_wrong_database_and_environment_fail_before_writes(self):
        self.db.database = "another"
        with self.assertRaisesRegex(AssetError, "DATABASE_MISMATCH"):
            self.repo.import_bundle(self.document, expected_namespace=NAMESPACE)
        self.db.database, self.db.env = "asset_prt", "ONLINE"
        with self.assertRaisesRegex(AssetError, "DATABASE_ENVIRONMENT_MISMATCH"):
            self.repo.import_bundle(self.document, expected_namespace=NAMESPACE)
        self.assertEqual({}, self.db.assets)

    def test_validation_precedes_connect(self):
        changed = deepcopy(self.document)
        changed["assets"][0]["contentDigest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(AssetError, "DIGEST_MISMATCH"):
            self.repo.import_bundle(changed, expected_namespace=NAMESPACE)
        self.assertEqual(0, self.db.connects)

    def test_namespace_and_missing_dependency_rejected(self):
        with self.assertRaisesRegex(AssetError, "DESTINATION_MISMATCH"):
            self.validator.validate(self.document, expected_namespace="different",
                                    expected_environment="PRT")
        changed = deepcopy(self.document)
        changed["assets"][-1]["dependencies"][0]["key"] = "missing"
        with self.assertRaises(AssetError):
            self.validate(self.resign(changed))

    def test_duplicate_unknown_fields_and_cycles_rejected(self):
        cases = []
        duplicate = deepcopy(self.document)
        duplicate["assets"].append(deepcopy(duplicate["assets"][0]))
        cases.append(duplicate)
        field = deepcopy(self.document)
        field["assets"][0]["unexpected"] = True
        cases.append(field)
        cycle = deepcopy(self.document)
        cycle["assets"][0]["dependencies"] = [{"kind": "WORKFLOW", "key": "activity-planning"}]
        cases.append(self.resign(cycle))
        for case in cases:
            with self.subTest():
                with self.assertRaises(AssetError):
                    self.validate(case)

    def test_runtime_skill_roundtrip_from_imported_bytes(self):
        self.repo.import_bundle(self.document, expected_namespace=NAMESPACE, dry_run=False)
        reader = AssetReader(self.repo, NAMESPACE)
        context = TrustedInvocationContext("SW-CONTRACTS-P1-CANDIDATE.1",
            RegistryContext("u1", "PRT"), InvocationScope("CONVERSATION", conversation_id="c1"), "q1")
        result = use_skill(UseSkillRequest("activity-planning/plan"), context, reader)
        self.assertIn("活动策划", result.content.instructions)
        self.assertEqual("PRT_CURRENT", result.artifact.selection)
        self.assertEqual(7, len(reader.versions(TrustedContext("u1", "PRT"), "activity-planning")))
        self.assertEqual({"skillKey", "assetId", "versionId"}, set(reader.list_skills(context.trusted_context)[0]))
        self.assertNotIn("definition", reader.list_workflows(context.trusted_context)[0])

    def test_wrong_owner_environment_no_repository_read(self):
        reader = AssetReader(self.repo, NAMESPACE)
        with self.assertRaisesRegex(AssetError, "ENVIRONMENT_MISMATCH"):
            reader.list_skills(TrustedContext("u1", "ONLINE"))
        self.assertEqual(0, self.db.connects)

    def test_corrupt_readback_rejected(self):
        self.repo.import_bundle(self.document, expected_namespace=NAMESPACE, dry_run=False)
        key = next(iter(self.db.assets))
        raw, expected = self.db.assets[key]
        self.db.assets[key] = (raw + b" ", expected)
        with self.assertRaisesRegex(AssetError, "READBACK_DIGEST_MISMATCH"):
            self.repo.read(NAMESPACE)

    def test_gray_uses_only_trusted_user_and_online_database(self):
        doc = make_bundle("ONLINE")
        gray = deepcopy(next(a for a in doc["assets"] if a["key"] == "activity-planning/copy"))
        gray["versionId"] = "v2"
        doc["assets"].append(gray)
        state = next(s for s in doc["serving"] if s["key"] == gray["key"])
        state["gray"], state["grayUserIds"] = "v2", ["gray-user"]
        bundle = self.validate(self.resign(doc))
        class Snapshot:
            environment = "ONLINE"
            validator = self.validator
            def read(inner, ns):
                return bundle
        reader = AssetReader(Snapshot(), NAMESPACE)
        gray_result = reader.load_skill(gray["key"], TrustedContext("gray-user", "ONLINE"))
        stable = reader.load_skill(gray["key"], TrustedContext("stable-user", "ONLINE"))
        self.assertEqual("v2", gray_result.resolution_evidence.version_id)
        self.assertEqual("ONLINE_GRAY", gray_result.resolution_evidence.selection)
        self.assertEqual("v1", stable.resolution_evidence.version_id)
        self.assertEqual("ONLINE_STABLE", stable.resolution_evidence.selection)

    def test_real_local_operations_and_confirmation_not_model_allowlisted(self):
        result = budget_activity({"participants": 3, "budgetMinor": 100}, TrustedContext("u1", "PRT"))
        self.assertEqual(33, result["perPersonMinor"])
        self.assertEqual(1, result["remainderMinor"])
        self.assertNotIn(CONFIRM_KEY, MODEL_ABILITY_KEYS)
        self.assertEqual({"selectedOptionId": "A", "confirmed": True},
            select_activity({"optionId": "A", "confirmed": True}, TrustedContext("u1", "PRT")))
        for values in ({"participants": True, "budgetMinor": 10},
                       {"participants": 0, "budgetMinor": 10}):
            with self.assertRaises(ValueError):
                budget_activity(values, TrustedContext("u1", "PRT"))

    def test_mutating_result_mapping_does_not_mutate_future_reads(self):
        self.repo.import_bundle(self.document, expected_namespace=NAMESPACE, dry_run=False)
        reader = AssetReader(self.repo, NAMESPACE)
        result = reader.resolve_workflow("activity-planning", TrustedContext("u1", "PRT"))
        result.definition["nodes"].clear()
        self.assertEqual(2, len(result.definition["nodes"]))
        ability = reader.resolve_ability("activity-planning.budget", TrustedContext("u1", "PRT"))
        self.assertEqual("v1", ability.version_id)
        self.assertEqual("activity-planning.budget", ability.operation_ref)


if __name__ == "__main__":
    unittest.main()
