"""Directed authoring relations persisted in the source draft transaction.

Revision snapshots retain prior bindings; removing a binding means it is absent
from the new source revision. Published dependency/version storage is separate.
"""

from typing import Literal, Protocol, TypeAlias, TypedDict, cast

from skillweave_contracts import parse_identifier, parse_skill_key

from .contracts import AssetKind, ManagedDraft, ManagementError

RelationType: TypeAlias = Literal[
    "SKILL_ABILITY",
    "SKILL_APPLICATION",
    "APPLICATION_ABILITY",
    "APPLICATION_COMPONENT",
    "WORKFLOW_SKILL",
]
RelationTarget: TypeAlias = tuple[AssetKind, str, RelationType]
SqlParams: TypeAlias = tuple[object, ...]


class DraftRelation(TypedDict):
    namespace: str
    sourceKind: AssetKind
    sourceKey: str
    sourceRevision: int
    targetKind: AssetKind
    targetKey: str
    relationType: RelationType


class QueryResult(Protocol):
    def fetchall(self) -> list[tuple[object, ...]]: ...


class RelationConnection(Protocol):
    def execute(self, query: str, params: SqlParams = ()) -> QueryResult: ...


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


def _relation_type(source: AssetKind, target: AssetKind) -> RelationType:
    value = f"{source}_{target}"
    allowed: frozenset[str] = frozenset(
        {
            "SKILL_ABILITY",
            "SKILL_APPLICATION",
            "APPLICATION_ABILITY",
            "APPLICATION_COMPONENT",
            "WORKFLOW_SKILL",
        }
    )
    if value not in allowed:
        raise ManagementError("INVALID_RELATION_TYPE")
    return cast(RelationType, value)


def _string_list(value: object, *, code: str, limit: int) -> list[str]:
    if type(value) is not list or len(value) > limit:
        raise ManagementError(code)
    if any(type(item) is not str for item in value):
        raise ManagementError(code)
    return cast(list[str], value)


def _binding_targets(draft: ManagedDraft) -> tuple[RelationTarget, ...]:
    ability_kind: AssetKind = "ABILITY"
    application_kind: AssetKind = "APPLICATION"
    component_kind: AssetKind = "COMPONENT"
    skill_kind: AssetKind = "SKILL"
    if draft.kind == "SKILL":
        groups: list[tuple[AssetKind, list[str]]] = [
            (
                kind,
                _string_list(draft.document.get(field, []), code="INVALID_BINDINGS", limit=64),
            )
            for field, kind in (
                ("abilityBindings", ability_kind),
                ("applicationBindings", application_kind),
            )
        ]
    elif draft.kind == "APPLICATION":
        dependencies = draft.document.get("dependencies", [])
        if type(dependencies) is not list or len(dependencies) > 128:
            raise ManagementError("INVALID_DEPENDENCIES")
        groups = [(kind, []) for kind in (ability_kind, component_kind)]
        by_kind: dict[AssetKind, list[str]] = dict(groups)
        for item in dependencies:
            if (
                type(item) is not dict
                or set(item) != {"kind", "key"}
                or type(item.get("kind")) is not str
                or item.get("kind") not in by_kind
                or type(item.get("key")) is not str
            ):
                raise ManagementError("INVALID_DEPENDENCIES")
            dependency = cast(dict[str, object], item)
            by_kind[cast(AssetKind, dependency["kind"])].append(cast(str, dependency["key"]))
    elif draft.kind == "WORKFLOW":
        nodes = draft.document.get("nodes", [])
        if type(nodes) is not list or len(nodes) > 64:
            raise ManagementError("INVALID_WORKFLOW_NODES")
        values: list[str] = []
        for node in nodes:
            if (
                type(node) is not dict
                or "skillKey" not in node
                or type(node.get("skillKey")) is not str
            ):
                raise ManagementError("INVALID_WORKFLOW_NODE")
            skill_key = cast(str, node["skillKey"])
            try:
                parse_skill_key(skill_key)
            except ValueError:
                raise ManagementError("INVALID_WORKFLOW_NODE") from None
            if skill_key not in values:
                values.append(skill_key)
        groups = [(skill_kind, values)]
    else:
        # Ability and Component currently declare no outgoing asset references.
        groups = []
    result: list[RelationTarget] = []
    for kind, values in groups:
        limit = 128 if draft.kind == "APPLICATION" else 64
        if len(values) > limit:
            raise ManagementError("INVALID_BINDINGS")
        for value in values:
            try:
                (parse_skill_key if kind == "SKILL" else parse_identifier)(value)
            except ValueError:
                raise ManagementError("INVALID_BINDINGS") from None
        if len(set(values)) != len(values):
            raise ManagementError("INVALID_BINDINGS")
        result.extend((kind, key, _relation_type(draft.kind, kind)) for key in values)
    return tuple(sorted(result))


def draft_relations(
    namespace: str, draft: ManagedDraft, revision: int
) -> tuple[DraftRelation, ...]:
    if namespace.startswith("skill-workspace:"):
        return ()
    return tuple(
        {
            "namespace": namespace,
            "sourceKind": draft.kind,
            "sourceKey": draft.key,
            "sourceRevision": revision,
            "targetKind": kind,
            "targetKey": key,
            "relationType": relation_type,
        }
        for kind, key, relation_type in _binding_targets(draft)
    )


def replace_draft_relations(
    connection: RelationConnection,
    namespace: str,
    draft: ManagedDraft,
    revision: int,
) -> None:
    relations = draft_relations(namespace, draft, revision)
    if namespace.startswith("skill-workspace:"):
        return
    connection.execute(
        "DELETE FROM a2flow_management_relations WHERE namespace=%s "
        "AND source_kind=%s AND source_key=%s AND source_revision=%s",
        (namespace, draft.kind, draft.key, revision),
    )
    for relation in relations:
        connection.execute(
            "INSERT INTO a2flow_management_relations "
            "(namespace,source_kind,source_key,source_revision,"
            "target_kind,target_key,relation_type) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (
                relation["namespace"],
                relation["sourceKind"],
                relation["sourceKey"],
                relation["sourceRevision"],
                relation["targetKind"],
                relation["targetKey"],
                relation["relationType"],
            ),
        )


def list_relations(
    connection: RelationConnection,
    namespace: str,
    kind: AssetKind,
    key: str,
    revision: int | None = None,
) -> tuple[DraftRelation, ...]:
    if revision is None:
        rows = connection.execute(
            "SELECT r.source_revision,r.target_kind,r.target_key,r.relation_type "
            "FROM a2flow_management_relations r JOIN a2flow_management_drafts d "
            "ON (r.namespace,r.source_kind,r.source_key,r.source_revision)="
            "(d.namespace,d.kind,d.asset_key,d.revision) "
            "WHERE r.namespace=%s AND r.source_kind=%s AND r.source_key=%s "
            "ORDER BY r.target_kind,r.target_key,r.relation_type",
            (namespace, kind, key),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT source_revision,target_kind,target_key,relation_type "
            "FROM a2flow_management_relations "
            "WHERE namespace=%s AND source_kind=%s AND source_key=%s AND source_revision=%s "
            "ORDER BY target_kind,target_key,relation_type",
            (namespace, kind, key, revision),
        ).fetchall()
    result: list[DraftRelation] = []
    for row_revision, target_kind, target_key, relation_type in rows:
        if (
            type(row_revision) is not int
            or type(target_kind) is not str
            or type(target_key) is not str
            or type(relation_type) is not str
        ):
            raise ManagementError("INVALID_RELATION_ROW", 500)
        result.append(
            {
                "namespace": namespace,
                "sourceKind": kind,
                "sourceKey": key,
                "sourceRevision": row_revision,
                "targetKind": cast(AssetKind, target_kind),
                "targetKey": target_key,
                "relationType": cast(RelationType, relation_type),
            }
        )
    return tuple(result)
