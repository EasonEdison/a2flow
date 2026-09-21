"""Directed authoring relations persisted in the source draft transaction.

Revision snapshots retain prior bindings; removing a binding means it is absent
from the new source revision. Published dependency/version storage is separate.
"""
from skillweave_contracts import parse_identifier, parse_skill_key

from .contracts import ManagementError

RELATION_DDL = (
    "CREATE TABLE IF NOT EXISTS a2flow_management_relations ("
    "namespace TEXT NOT NULL, source_kind TEXT NOT NULL, source_key TEXT NOT NULL, "
    "source_revision BIGINT NOT NULL CHECK(source_revision > 0), "
    "target_kind TEXT NOT NULL, target_key TEXT NOT NULL, relation_type TEXT NOT NULL, "
    "PRIMARY KEY(namespace,source_kind,source_key,source_revision,"
    "target_kind,target_key,relation_type))",
    "CREATE INDEX IF NOT EXISTS a2flow_management_relations_target_idx ON "
    "a2flow_management_relations(namespace,target_kind,target_key,relation_type)",
)


def _binding_targets(draft):
    if draft.kind == "SKILL":
        groups = [(kind, draft.document.get(field, [])) for field, kind in (
            ("abilityBindings", "ABILITY"), ("applicationBindings", "APPLICATION"))]
    elif draft.kind == "APPLICATION":
        dependencies = draft.document.get("dependencies", [])
        if type(dependencies) is not list or len(dependencies) > 128:
            raise ManagementError("INVALID_DEPENDENCIES")
        groups = [(kind, []) for kind in ("ABILITY", "COMPONENT")]
        by_kind = dict(groups)
        for item in dependencies:
            if (type(item) is not dict or set(item) != {"kind", "key"}
                    or type(item.get("kind")) is not str
                    or item.get("kind") not in by_kind):
                raise ManagementError("INVALID_DEPENDENCIES")
            by_kind[item["kind"]].append(item["key"])
    elif draft.kind == "WORKFLOW":
        nodes = draft.document.get("nodes", [])
        if type(nodes) is not list or len(nodes) > 64:
            raise ManagementError("INVALID_WORKFLOW_NODES")
        values = []
        for node in nodes:
            if type(node) is not dict or "skillKey" not in node:
                raise ManagementError("INVALID_WORKFLOW_NODE")
            try:
                parse_skill_key(node["skillKey"])
            except Exception:
                raise ManagementError("INVALID_WORKFLOW_NODE") from None
            if node["skillKey"] not in values:
                values.append(node["skillKey"])
        groups = [("SKILL", values)]
    else:
        # Ability and Component currently declare no outgoing asset references.
        groups = []
    result = []
    for kind, values in groups:
        limit = 128 if draft.kind == "APPLICATION" else 64
        if type(values) is not list or len(values) > limit:
            raise ManagementError("INVALID_BINDINGS")
        for value in values:
            try:
                (parse_skill_key if kind == "SKILL" else parse_identifier)(value)
            except Exception:
                raise ManagementError("INVALID_BINDINGS") from None
        if len(set(values)) != len(values):
            raise ManagementError("INVALID_BINDINGS")
        result.extend((kind, key, draft.kind + "_" + kind) for key in values)
    return sorted(result)


def draft_relations(namespace, draft, revision):
    if namespace.startswith("skill-workspace:"):
        return ()
    return tuple({
        "namespace": namespace, "sourceKind": draft.kind, "sourceKey": draft.key,
        "sourceRevision": revision, "targetKind": kind, "targetKey": key,
        "relationType": relation_type,
    } for kind, key, relation_type in _binding_targets(draft))


def replace_draft_relations(connection, namespace, draft, revision):
    relations = draft_relations(namespace, draft, revision)
    if namespace.startswith("skill-workspace:"):
        return
    connection.execute(
        "DELETE FROM a2flow_management_relations WHERE namespace=%s "
        "AND source_kind=%s AND source_key=%s AND source_revision=%s",
        (namespace, draft.kind, draft.key, revision))
    for relation in relations:
        connection.execute(
            "INSERT INTO a2flow_management_relations "
            "(namespace,source_kind,source_key,source_revision,target_kind,target_key,relation_type) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s)",
            tuple(relation[field] for field in (
                "namespace", "sourceKind", "sourceKey", "sourceRevision",
                "targetKind", "targetKey", "relationType")))


def list_relations(connection, namespace, kind, key, revision=None):
    if revision is None:
        rows = connection.execute(
            "SELECT r.source_revision,r.target_kind,r.target_key,r.relation_type "
            "FROM a2flow_management_relations r JOIN a2flow_management_drafts d "
            "ON (r.namespace,r.source_kind,r.source_key,r.source_revision)="
            "(d.namespace,d.kind,d.asset_key,d.revision) "
            "WHERE r.namespace=%s AND r.source_kind=%s AND r.source_key=%s "
            "ORDER BY r.target_kind,r.target_key,r.relation_type",
            (namespace, kind, key)).fetchall()
    else:
        rows = connection.execute(
            "SELECT source_revision,target_kind,target_key,relation_type "
            "FROM a2flow_management_relations "
            "WHERE namespace=%s AND source_kind=%s AND source_key=%s AND source_revision=%s "
            "ORDER BY target_kind,target_key,relation_type",
            (namespace, kind, key, revision)).fetchall()
    return tuple({
        "namespace": namespace, "sourceKind": kind, "sourceKey": key,
        "sourceRevision": revision, "targetKind": target_kind,
        "targetKey": target_key, "relationType": relation_type,
    } for revision, target_kind, target_key, relation_type in rows)
