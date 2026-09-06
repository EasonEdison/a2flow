#!/usr/bin/env python3
"""Validate the provisional Phase 1 consumer examples with the Python standard library.

This is a documentation-fixture check, not the product graph validator or Runtime proof.
"""

import json
import os
import re


HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(HERE, name), "r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


graph = load("phase1-valid-parallel-choice.json")
cases = load("phase1-validation-cases.json")

require(graph["_meta"]["baseline"] == "SW-P1-20260907.2", "graph baseline")
require(cases["_meta"]["baseline"] == "SW-P1-20260907.2", "cases baseline")
require(graph["_meta"]["sharedSchemaAuthority"] is False, "fixture must stay non-authoritative")
require(cases["_meta"]["productValidatorEvidence"] is False, "fixture is not product evidence")

nodes = graph["nodes"]
edges = graph["edges"]
node_by_key = {node["nodeKey"]: node for node in nodes}
require(len(node_by_key) == len(nodes), "duplicate node key")
require(len({(edge["from"], edge["to"], edge.get("routeKey")) for edge in edges}) == len(edges), "duplicate edge")

for edge in edges:
    require(edge["from"] in node_by_key, "unknown edge source")
    require(edge["to"] in node_by_key, "unknown edge target")

for kind in ("START", "FINALIZER", "END"):
    require(sum(1 for node in nodes if node["kind"] == kind) == 1, "expected one " + kind)

allowed_failure = {"REQUIRED", "ALLOW_SKIP"}
require(all(node["failureRequirement"] in allowed_failure for node in nodes), "unknown failure requirement")

skill_key_pattern = re.compile(r"^[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*$")
skill_nodes = [node for node in nodes if node["kind"] == "SKILL"]
require(
    all("skillKey" in node and "skillRef" not in node for node in skill_nodes),
    "skill node must use exact skillKey",
)
node_skill_keys = {node["skillKey"] for node in skill_nodes}
require(all(skill_key_pattern.fullmatch(key) for key in node_skill_keys), "invalid skillKey grammar")
skill_configuration_refs = [
    ref for ref in graph["configurationRefs"] if ref["assetType"] == "SKILL"
]
require(
    all("skillKey" in ref and "logicalRef" not in ref for ref in skill_configuration_refs),
    "SKILL configuration reference must use explicit skillKey",
)
require(
    node_skill_keys == {ref["skillKey"] for ref in skill_configuration_refs},
    "node and configuration skillKey sets must match",
)

adjacency = {key: [] for key in node_by_key}
indegree = {key: 0 for key in node_by_key}
for edge in edges:
    adjacency[edge["from"]].append(edge["to"])
    indegree[edge["to"]] += 1
queue = sorted([key for key, degree in indegree.items() if degree == 0])
visited = []
while queue:
    current = queue.pop(0)
    visited.append(current)
    for target in adjacency[current]:
        indegree[target] -= 1
        if indegree[target] == 0:
            queue.append(target)
            queue.sort()
require(len(visited) == len(nodes), "graph must be acyclic and fully topologically sortable")
reachable = set()
frontier = ["start"]
while frontier:
    current = frontier.pop()
    if current in reachable:
        continue
    reachable.add(current)
    frontier.extend(adjacency[current])
require(reachable == set(node_by_key), "all nodes must be reachable from START")

for region in graph["decisionRegions"]:
    decision = node_by_key[region["decisionNodeKey"]]
    require(decision["kind"] == "AI_DECISION", "decision region source kind")
    require(node_by_key[region["mergeNodeKey"]]["kind"] == "CONDITION_MERGE", "decision merge kind")
    candidate_map = {candidate["candidateKey"]: candidate["targetNodeKey"] for candidate in decision["candidates"]}
    require(set(candidate_map) == set(region["candidateKeys"]), "decision candidate set")
    conditional_map = {edge["routeKey"]: edge["to"] for edge in edges if edge["from"] == decision["nodeKey"] and edge["edgeKind"] == "CONDITIONAL"}
    require(candidate_map == conditional_map, "decision candidates must match conditional edges")
    merge_inputs = {edge["from"] for edge in edges if edge["to"] == region["mergeNodeKey"]}
    require(set(candidate_map.values()) == merge_inputs, "selected candidates must converge through condition merge")
    require(bool(decision.get("selectionApplicationRef")), "decision selection application")

for region in graph["parallelRegions"]:
    split = region["splitNodeKey"]
    join = region["joinNodeKey"]
    require(node_by_key[split]["kind"] == "PARALLEL_SPLIT", "parallel split kind")
    require(node_by_key[join]["kind"] == "PARALLEL_JOIN", "parallel join kind")
    branches = set(region["branchKeys"])
    split_branches = {edge["branchKey"] for edge in edges if edge["from"] == split and edge["edgeKind"] == "PARALLEL"}
    require(branches == split_branches, "parallel split branch set")
    require(branches == set(region["branchExitNodeKeys"]), "parallel exit branch set")
    join_edges = {(edge.get("branchKey"), edge["from"]) for edge in edges if edge["to"] == join}
    expected_join_edges = {(branch, exit_node) for branch, exit_node in region["branchExitNodeKeys"].items()}
    require(join_edges == expected_join_edges, "parallel join membership")

serialized = json.dumps(graph, ensure_ascii=False)
for forbidden in ('"environment"', '"userId"', '"credentials"', '"secret"', '"retryPolicy"'):
    require(forbidden not in serialized, "forbidden authored field: " + forbidden)

expected_static = {
    "GRAPH_CYCLE",
    "DECISION_TARGET_UNKNOWN",
    "PARALLEL_BRANCH_MISMATCH",
    "PARALLEL_NESTING_NOT_SUPPORTED",
    "GRAPH_UNREACHABLE",
}
actual_static = {issue for case in cases["staticCases"] for issue in case["expectedIssues"]}
require(actual_static == expected_static, "static validation coverage")

expected_runtime_ids = {
    "a-waits-b-continues",
    "allow-skip-failure-can-join",
    "required-failure-blocks",
    "a2ui-owning-node-retry",
    "accepted-stop-blocks-finalizer",
}
require({case["caseId"] for case in cases["runtimeCases"]} == expected_runtime_ids, "runtime case coverage")

require("contextCases" in cases, "context propagation cases missing")
expected_context_ids = {
    "transitive-sequence-context",
    "join-executed-branches-context",
}
context_by_id = {case["caseId"]: case for case in cases["contextCases"]}
require(set(context_by_id) == expected_context_ids, "context case coverage")

sequence_context = context_by_id["transitive-sequence-context"]
require(sequence_context["topology"] == ["skill_a", "skill_b", "skill_c"], "transitive topology")
sequence_expected = {"skill_a", "skill_b"}
sequence_executed = {entry["nodeKey"]: entry for entry in sequence_context["executedAncestorNodes"]}
require(set(sequence_context["expectedContextNodeKeys"]) == sequence_expected, "skill C must receive A and B final context")
require(set(sequence_executed) == sequence_expected, "sequence executed ancestors")
require(
    all(entry.get("status") and entry.get("finalResultRef") for entry in sequence_executed.values()),
    "sequence ancestor facts must carry status and final result reference",
)

join_context = context_by_id["join-executed-branches-context"]
join_expected = {"decision_a", "a_fast", "merge_a", "b1", "b2", "join"}
join_executed = {entry["nodeKey"]: entry for entry in join_context["executedAncestorNodes"]}
require(set(join_context["expectedContextNodeKeys"]) == join_expected, "finalizer must receive the executed branch ancestors")
require(set(join_executed) == join_expected, "join executed ancestors")
require(
    all(entry.get("status") and entry.get("finalResultRef") for entry in join_executed.values()),
    "join ancestor facts must carry status and final result reference",
)
join_absent = set(join_context["expectedAbsentNodeKeys"])
require(join_absent == {"a_review"}, "unselected branch result must stay absent")
require(join_absent.isdisjoint(join_executed), "unselected branch must not have an executed result")

print(
    "phase1-workflow-fixtures: PASS nodes={0} edges={1} staticCases={2} runtimeCases={3} contextCases={4}".format(
        len(nodes),
        len(edges),
        len(cases["staticCases"]),
        len(cases["runtimeCases"]),
        len(cases["contextCases"]),
    )
)
