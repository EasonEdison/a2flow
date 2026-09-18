import unittest

from a2flow_asset_store.records import Asset, Bundle, canonical, digest
from a2flow_management import ManagedDraft, MemoryDraftRepository, TrustedManagementContext
from a2flow_management.dependencies import DependencyService


NAMESPACE = "dependency-tests"


def asset(kind, key, version, definition, dependencies=()):
    value = {
        "kind": kind,
        "key": key,
        "assetId": kind.lower() + "-" + key.replace("/", "-"),
        "versionId": version,
        "definition": definition,
        "dependencies": [{"kind": item[0], "key": item[1]} for item in dependencies],
    }
    data = canonical(value)
    return Asset(kind, key, value["assetId"], version, data, digest(data))


class Repository:
    environment = "PRT"

    def __init__(self):
        assets = (
            asset("ABILITY", "ability.one", "v1", {}),
            asset("ABILITY", "ability.one", "v2", {}),
            asset("ABILITY", "ability.missing-release", "v1", {}),
            asset("COMPONENT", "component/catalog", "v1", {}),
            asset("APPLICATION", "app/card", "v1", {
                "asset": {"componentCatalogRef": "component/catalog"},
                "actionPolicies": [{"abilityReleaseRef": "ability.one@v1"}],
            }, (("COMPONENT", "component/catalog"), ("ABILITY", "ability.one"))),
            asset("SKILL", "skill/root", "v1", {},
                  (("ABILITY", "ability.one"), ("APPLICATION", "app/card"))),
            asset("WORKFLOW", "workflow/root", "v1", {
                "nodes": [{"nodeId": "one", "skillKey": "skill/root"}],
            }, (("SKILL", "skill/root"),)),
        )
        serving = [
            {"kind": item.kind, "key": item.key, "current": "v2" if item.kind == "ABILITY" and item.key == "ability.one" else item.version_id,
             "stable": None, "gray": None, "grayUserIds": []}
            for item in assets if not (item.kind == "ABILITY" and item.key == "ability.one" and item.version_id == "v1")
        ]
        self.bundle = Bundle(NAMESPACE, "PRT", assets, canonical(serving))
        self.read_count = 0

    def read(self, namespace):
        self.read_count += 1
        self.assert_namespace = namespace
        return self.bundle


class DependencyServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = Repository()
        self.drafts = MemoryDraftRepository("PRT")
        self.service = DependencyService(self.repository, self.drafts, NAMESPACE)
        self.admin = TrustedManagementContext("admin", "PRT", frozenset({"ADMIN"}))
        self.user = TrustedManagementContext("user", "PRT", frozenset({"USER"}))

    def test_published_graph_extracts_schema_paths_exact_release_and_reverse(self):
        graph = self.service.inspect(self.user, "APPLICATION", "app/card")
        edges = {(edge["toKind"], edge["toKey"], edge["path"]): edge for edge in graph["upstream"]}
        self.assertEqual("exact-release", edges[("ABILITY", "ability.one", "/definition/actionPolicies/0/abilityReleaseRef")]["selectorType"])
        self.assertEqual("v1", edges[("ABILITY", "ability.one", "/definition/actionPolicies/0/abilityReleaseRef")]["requestedVersionId"])
        self.assertEqual("retained", edges[("ABILITY", "ability.one", "/definition/actionPolicies/0/abilityReleaseRef")]["target"]["source"])
        self.assertEqual("v1", edges[("ABILITY", "ability.one", "/definition/actionPolicies/0/abilityReleaseRef")]["target"]["versionId"])
        self.assertIn(("SKILL", "skill/root"), {(edge["fromKind"], edge["fromKey"]) for edge in graph["dependents"]})
        self.assertEqual(1, self.repository.read_count)
        self.assertFalse(graph["incomplete"])

    def test_admin_sees_saved_draft_separately_but_user_does_not_leak_it(self):
        current = ManagedDraft.create("SKILL", "skill/root", 0, {
            "abilityBindings": ["ability.missing-release"], "applicationBindings": [],
        }, "admin")
        self.drafts.save(NAMESPACE, current, 0)
        draft = ManagedDraft.create("SKILL", "private/draft", 0, {
            "abilityBindings": ["ability.one"], "applicationBindings": [],
        }, "admin")
        self.drafts.save(NAMESPACE, draft, 0)
        inspected = self.service.inspect(self.admin, "SKILL", "skill/root")
        self.assertIn(("ability.missing-release", "saved-draft"), {
            (edge["toKey"], edge["source"]) for edge in inspected["upstream"]})
        admin = self.service.inspect(self.admin, "ABILITY", "ability.one")
        self.assertIn(("SKILL", "private/draft", "saved-draft"), {
            (edge["fromKind"], edge["fromKey"], edge["source"]) for edge in admin["dependents"]})
        self.assertIn(("WORKFLOW", "workflow/root", 2), {
            (edge["fromKind"], edge["fromKey"], edge["depth"]) for edge in admin["dependents"]})
        user = self.service.inspect(self.user, "ABILITY", "ability.one")
        self.assertNotIn("private/draft", repr(user))

    def test_missing_exact_release_is_actionable_and_never_falls_back(self):
        document = self.repository.bundle.assets[4].document
        changed = {**document, "definition": {
            **document["definition"],
            "actionPolicies": [{"abilityReleaseRef": "ability.missing-release@v9"}],
        }, "dependencies": [{"kind": "COMPONENT", "key": "component/catalog"},
                             {"kind": "ABILITY", "key": "ability.missing-release"}]}
        replacement = asset("APPLICATION", "app/card", "v1", changed["definition"],
                            (("COMPONENT", "component/catalog"), ("ABILITY", "ability.missing-release")))
        values = list(self.repository.bundle.assets)
        values[4] = replacement
        self.repository.bundle = Bundle(NAMESPACE, "PRT", tuple(values), self.repository.bundle.serving_data)
        graph = self.service.inspect(self.user, "APPLICATION", "app/card")
        missing = next(edge for edge in graph["upstream"] if edge["toKey"] == "ability.missing-release")
        self.assertEqual("MISSING_EXACT_VERSION", missing["error"])
        self.assertEqual("missing", missing["target"]["status"])
        self.assertTrue(graph["incomplete"])
        self.assertEqual([{"kind": "ABILITY", "key": "ability.missing-release", "versionId": "v9"}], graph["missing"])
        self.assertEqual([], graph["unresolved"])

    def test_bounds_mark_result_truncated_and_read_is_read_only(self):
        graph = self.service.inspect(self.user, "WORKFLOW", "workflow/root", max_nodes=2, max_edges=1)
        self.assertTrue(graph["truncated"])
        self.assertTrue(graph["incomplete"])
        self.assertEqual(1, len(graph["upstream"]))
        self.assertFalse(hasattr(self.repository, "writes"))

    def test_environment_mismatch_fails_closed(self):
        context = TrustedManagementContext("user", "ONLINE", frozenset({"USER"}))
        with self.assertRaisesRegex(Exception, "TRUSTED_ENVIRONMENT_MISMATCH"):
            self.service.inspect(context, "SKILL", "skill/root")

    def test_node_and_edge_budgets_are_shared_hard_output_bounds(self):
        targets = tuple(asset("ABILITY", f"fan/{index}", "v1", {}) for index in range(6))
        root = asset("SKILL", "fan/root", "v1", {},
                     tuple(("ABILITY", f"fan/{index}") for index in range(6)))
        reverse = tuple(asset("SKILL", f"reverse/{index}", "v1", {},
                              (("ABILITY", "ability.one"),)) for index in range(6))
        assets = self.repository.bundle.assets + targets + (root,) + reverse
        serving = list(self.repository.bundle.serving)
        serving.extend({"kind": item.kind, "key": item.key, "current": item.version_id,
                        "stable": None, "gray": None, "grayUserIds": []}
                       for item in targets + (root,) + reverse)
        self.repository.bundle = Bundle(NAMESPACE, "PRT", assets, canonical(serving))
        direct = self.service.inspect(self.user, "SKILL", "fan/root", max_nodes=3, max_edges=9)
        self.assertLessEqual(direct["counts"]["nodes"], 3)
        self.assertLessEqual(direct["counts"]["edges"], 9)
        self.assertEqual(2, len(direct["upstream"]))
        self.assertTrue(direct["truncated"])
        fanout = self.service.inspect(self.user, "ABILITY", "ability.one", max_nodes=3, max_edges=9)
        self.assertLessEqual(fanout["counts"]["nodes"], 3)
        self.assertGreaterEqual(len(fanout["dependents"]), 1)
        self.assertLessEqual(len(fanout["dependents"]), 2)
        self.assertTrue(fanout["truncated"])
        mixed = self.service.inspect(self.user, "APPLICATION", "app/card", max_nodes=4, max_edges=3)
        self.assertLessEqual(mixed["counts"]["nodes"], 4)
        self.assertLessEqual(mixed["counts"]["edges"], 3)

    def test_depth_boundary_returns_direct_edge_without_traversing_beyond_it(self):
        graph = self.service.inspect(self.user, "WORKFLOW", "workflow/root", max_depth=0)
        self.assertEqual(1, len(graph["upstream"]))
        self.assertEqual("skill/root", graph["upstream"][0]["toKey"])
        self.assertTrue(graph["truncated"])
        self.assertNotIn("ability.one", {edge["toKey"] for edge in graph["upstream"]})

    def test_unrelated_malformed_draft_does_not_taint_graph(self):
        unrelated = ManagedDraft.create("SKILL", "unrelated/bad", 0, {
            "abilityBindings": "invalid", "applicationBindings": [],
        }, "admin")
        self.drafts.save(NAMESPACE, unrelated, 0)
        graph = self.service.inspect(self.admin, "APPLICATION", "app/card")
        self.assertFalse(graph["incomplete"])
        self.assertEqual([], graph["diagnostics"])

    def test_relevant_malformed_source_reports_versioned_location(self):
        malformed = ManagedDraft.create("SKILL", "skill/root", 0, {
            "abilityBindings": ["ability.one", 7], "applicationBindings": [],
        }, "admin")
        saved = self.drafts.save(NAMESPACE, malformed, 0)
        graph = self.service.inspect(
            self.admin, "SKILL", "skill/root", root_sources=("saved-draft",))
        self.assertTrue(graph["incomplete"])
        self.assertEqual("saved-draft", graph["diagnostics"][0]["source"])
        self.assertEqual(saved.revision, graph["diagnostics"][0]["revision"])
        self.assertEqual(["/abilityBindings/1"], graph["diagnostics"][0]["paths"])

    def test_saved_candidate_isolated_from_old_published_missing_dependency(self):
        old = asset("SKILL", "skill/root", "v1", {},
                    (("ABILITY", "old/missing"),))
        assets = tuple(old if item.kind == "SKILL" and item.key == "skill/root" else item
                       for item in self.repository.bundle.assets)
        self.repository.bundle = Bundle(
            NAMESPACE, "PRT", assets, self.repository.bundle.serving_data)
        corrected = ManagedDraft.create("SKILL", "skill/root", 0, {
            "abilityBindings": ["ability.one"], "applicationBindings": [],
        }, "admin")
        self.drafts.save(NAMESPACE, corrected, 0)
        combined = self.service.inspect(self.admin, "SKILL", "skill/root")
        candidate = self.service.inspect(
            self.admin, "SKILL", "skill/root", root_sources=("saved-draft",))
        self.assertTrue(combined["incomplete"])
        self.assertFalse(candidate["incomplete"])
        self.assertEqual({"ability.one"}, {edge["toKey"] for edge in candidate["upstream"]})

    def test_source_versions_keep_two_retained_references_distinct(self):
        second = asset("APPLICATION", "app/other", "v1", {
            "actionPolicies": [{"abilityReleaseRef": "ability.one@v2"}],
        }, (("ABILITY", "ability.one"),))
        assets = self.repository.bundle.assets + (second,)
        serving = list(self.repository.bundle.serving) + [{
            "kind": "APPLICATION", "key": "app/other", "current": "v1",
            "stable": None, "gray": None, "grayUserIds": [],
        }]
        self.repository.bundle = Bundle(NAMESPACE, "PRT", assets, canonical(serving))
        graph = self.service.inspect(self.user, "ABILITY", "ability.one")
        exact = [edge for edge in graph["dependents"]
                 if edge["selectorType"] == "exact-release"]
        self.assertEqual({"v1", "v2"}, {edge["requestedVersionId"] for edge in exact})
        self.assertEqual({"v1", "v2"}, {edge["target"]["versionId"] for edge in exact})
        labels = {edge["requestedVersionId"]: edge["targetsInspectedVersion"] for edge in exact}
        self.assertEqual({"v1": False, "v2": True}, labels)
        self.assertTrue(all("versionId" in edge["from"] for edge in exact))

    def test_admin_root_variants_are_budgeted_and_user_never_sees_draft(self):
        draft = ManagedDraft.create("SKILL", "skill/root", 0, {
            "abilityBindings": ["ability.one"], "applicationBindings": [],
        }, "admin")
        self.drafts.save(NAMESPACE, draft, 0)
        admin = self.service.inspect(self.admin, "SKILL", "skill/root", max_nodes=1)
        self.assertEqual(1, admin["counts"]["nodes"])
        self.assertEqual(1, len(admin["rootVariants"]))
        self.assertTrue(admin["truncated"])
        user = self.service.inspect(self.user, "SKILL", "skill/root")
        self.assertNotIn("saved-draft", repr(user))

    def test_online_selection_uses_only_authenticated_user_gray_evidence(self):
        repository = Repository()
        repository.environment = "ONLINE"
        serving = []
        for state in repository.bundle.serving:
            value = dict(state)
            value["stable"] = value["current"]
            if value["kind"] == "ABILITY" and value["key"] == "ability.one":
                value["stable"] = "v1"
                value["gray"] = "v2"
                value["grayUserIds"] = ["gray-user"]
            serving.append(value)
        repository.bundle = Bundle(NAMESPACE, "ONLINE", repository.bundle.assets,
                                   canonical(serving))
        service = DependencyService(
            repository, MemoryDraftRepository("ONLINE"), NAMESPACE)
        gray = service.inspect(
            TrustedManagementContext("gray-user", "ONLINE", frozenset({"USER"})),
            "ABILITY", "ability.one")
        stable = service.inspect(
            TrustedManagementContext("stable-user", "ONLINE", frozenset({"USER"})),
            "ABILITY", "ability.one")
        self.assertEqual(("v2", "ONLINE_GRAY"),
                         (gray["root"]["versionId"], gray["root"]["selection"]))
        self.assertEqual(("v1", "ONLINE_STABLE"),
                         (stable["root"]["versionId"], stable["root"]["selection"]))
        self.assertNotIn("grayUserIds", repr(gray))


if __name__ == "__main__":
    unittest.main()
