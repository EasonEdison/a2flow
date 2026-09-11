"""MVP08 committed display material. Reads never construct or invoke a graph."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import re

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import ActionRejected, json_copy
from .postgres_projection import PostgresProjection
from .serialization import decode
from .service import require_owner

VIEW_LIMIT = 192 * 1024
NODE_STATES = frozenset({"PENDING", "RUNNING", "WAITING", "SUCCEEDED", "UNCONFIRMED", "STOPPED"})
DDL = (
    """CREATE TABLE IF NOT EXISTS runtime_mvp_catalog (
       user_id TEXT NOT NULL, environment TEXT NOT NULL, last_seq BIGINT NOT NULL DEFAULT 0,
       PRIMARY KEY(user_id,environment), CHECK(last_seq >= 0))""",
    """CREATE TABLE IF NOT EXISTS runtime_mvp_views (
       user_id TEXT NOT NULL, environment TEXT NOT NULL, run_id TEXT NOT NULL,
       catalog_seq BIGINT NOT NULL, revision BIGINT NOT NULL DEFAULT 0,
       document JSONB NOT NULL,
       PRIMARY KEY(user_id,environment,run_id),
       UNIQUE(user_id,environment,catalog_seq),
       FOREIGN KEY(user_id,environment,run_id) REFERENCES runtime_runs,
       CHECK(catalog_seq > 0), CHECK(revision >= 0))""",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def bounded(value):
    copied = json_copy(value)
    if len(json.dumps(copied, ensure_ascii=False, allow_nan=False).encode()) > VIEW_LIMIT:
        raise ActionRejected("VIEW_LIMIT_EXCEEDED")
    return copied


def initial_view(run, definition, effective_versions):
    versions = dict(effective_versions)
    workflow_versions = [version for key, version in versions.items() if key.startswith("WORKFLOW:")]
    if len(workflow_versions) != 1:
        raise ActionRejected("WORKFLOW_VERSION_REQUIRED")
    return bounded({
        "schemaVersion": "mvp08.1", "runId": run.run_id,
        "definitionKey": run.definition_key, "title": run.definition_key,
        "definitionVersion": workflow_versions[0], "createdAt": now(),
        "nodes": [{"nodeId": node["nodeId"], "title": node["skillKey"], "order": index,
                   "status": "PENDING", "summary": None}
                  for index, node in enumerate(definition["nodes"])],
        "cards": [], "outputs": [], "availability": "AVAILABLE",
    })


def change_node(view, node_id, status, summary=None):
    if status not in NODE_STATES or (summary is not None and type(summary) is not str):
        raise ActionRejected("INVALID_NODE_VIEW")
    matches = [node for node in view["nodes"] if node["nodeId"] == node_id]
    if len(matches) != 1:
        raise ActionRejected("NODE_NOT_FOUND")
    node = matches[0]
    if node["status"] in {"SUCCEEDED", "STOPPED"} and status != node["status"]:
        raise ActionRejected("NODE_VIEW_TERMINAL")
    node.update(status=status, summary=summary)
    return view


def put_output(view, node_id, kind, content):
    if kind not in {"MODEL_TEXT", "ACTION_RESULT"}:
        raise ActionRejected("INVALID_OUTPUT_KIND")
    if kind == "MODEL_TEXT" and type(content) is not str:
        raise ActionRejected("INVALID_OUTPUT_CONTENT")
    value = {"nodeId": node_id, "kind": kind, "content": json_copy(content)}
    existing = next((item for item in view["outputs"]
                     if item["nodeId"] == node_id and item["kind"] == kind), None)
    if existing is not None:
        if existing != value:
            raise ActionRejected("OUTPUT_BINDING_CONFLICT")
        return view
    if len(view["outputs"]) >= 8 or not any(n["nodeId"] == node_id for n in view["nodes"]):
        raise ActionRejected("INVALID_OUTPUT_VIEW")
    view["outputs"].append(value)
    return bounded(view)


def complete_node(view, node_id, content):
    put_output(view, node_id, "MODEL_TEXT", content)
    change_node(view, node_id, "SUCCEEDED", content[:240])
    return view


def _interaction_card(interaction, node_ids):
    if interaction.display_json is None:
        return None
    try:
        card = json.loads(interaction.display_json)
    except (TypeError, ValueError, RecursionError):
        raise ActionRejected("PROJECTION_UNAVAILABLE") from None
    scope = interaction.context.invocation_scope
    if (type(card) is not dict or card.get("interactionId") != interaction.interaction_id
            or card.get("nodeId") != scope.node_id or card.get("nodeId") not in node_ids
            or type(card.get("cardId")) is not str or not card["cardId"]):
        raise ActionRejected("PROJECTION_UNAVAILABLE")
    return card


def project_view(document, revision, lifecycle, lifecycle_revision, interactions):
    view = bounded(document)
    if lifecycle not in {"RUNNING", "STOPPED", "SUCCEEDED"}:
        raise ActionRejected("PROJECTION_UNAVAILABLE")
    node_ids = frozenset(node["nodeId"] for node in view["nodes"])
    cards = []
    for interaction in interactions.values():
        card = _interaction_card(interaction, node_ids)
        scope = interaction.context.invocation_scope
        if scope.node_id not in node_ids:
            raise ActionRejected("PROJECTION_UNAVAILABLE")
        if card is not None:
            cards.append(card)
        if lifecycle == "RUNNING" and interaction.phase == "WAITING":
            node = next(item for item in view["nodes"] if item["nodeId"] == scope.node_id)
            if node["status"] not in {"SUCCEEDED", "STOPPED"}:
                node["status"] = "WAITING"
        for attempt in interaction.attempts:
            if (attempt.status == "EXECUTED" and attempt.business_success
                    and attempt.result_json is not None):
                try:
                    result = json.loads(attempt.result_json)
                except (TypeError, ValueError, RecursionError):
                    raise ActionRejected("PROJECTION_UNAVAILABLE") from None
                put_output(view, scope.node_id, "ACTION_RESULT", result)
    if len(cards) > 16:
        raise ActionRejected("PROJECTION_UNAVAILABLE")
    view["cards"] = cards
    view.update(lifecycle=lifecycle, revision=f"{revision}:{lifecycle_revision}", observedAt=now())
    for node in view["nodes"]:
        if node["status"] not in NODE_STATES:
            raise ActionRejected("PROJECTION_UNAVAILABLE")
        if lifecycle == "STOPPED" and node["status"] != "SUCCEEDED":
            node["status"] = "STOPPED"
    for card in view["cards"]:
        interaction = interactions[card["interactionId"]]
        waiting = (lifecycle == "RUNNING" and interaction.phase == "WAITING"
                   and interaction.run_active and interaction.node_waiting
                   and not interaction.resume_started)
        card["state"] = "WAITING" if waiting else (
            "INVALIDATED" if lifecycle == "STOPPED" or interaction.phase == "INVALIDATED"
            or not interaction.run_active else "READ_ONLY")
        card["actionEligibility"] = "REVALIDATION_REQUIRED" if waiting else "NOT_OPERABLE"
    return bounded(view)


class PostgresMvpView(PostgresProjection):
    """Runtime-owned display writes with independent, short PG transactions."""

    @contextmanager
    def _write(self):
        connection = self._connect(
            self._conninfo, autocommit=True, row_factory=dict_row, connect_timeout=2,
            options="-c statement_timeout=1500 -c lock_timeout=500",
            application_name="a2flow-mvp08-view",
        )
        try:
            with connection.transaction():
                yield connection
        finally:
            connection.close()

    def setup(self):
        with self._write() as connection:
            for sql in DDL:
                connection.execute(sql)

    def ensure(self, run, definition, effective_versions):
        require_owner(run.owner)
        document = initial_view(run, definition, effective_versions)
        key = self._key(run.owner, run.run_id)
        with self._write() as connection:
            connection.execute(
                "INSERT INTO runtime_mvp_catalog(user_id,environment) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                key[:2])
            connection.execute(
                "SELECT last_seq FROM runtime_mvp_catalog WHERE user_id=%s AND environment=%s FOR UPDATE",
                key[:2]).fetchone()
            existing = connection.execute(
                "SELECT document FROM runtime_mvp_views WHERE user_id=%s AND environment=%s AND run_id=%s",
                key).fetchone()
            if existing is not None:
                saved = existing["document"]
                if (saved["definitionKey"], saved["definitionVersion"]) != (
                    document["definitionKey"], document["definitionVersion"]
                ):
                    raise ActionRejected("RESET_REQUIRED")
                return
            row = connection.execute(
                "UPDATE runtime_mvp_catalog SET last_seq=last_seq+1 WHERE user_id=%s AND environment=%s RETURNING last_seq",
                key[:2]).fetchone()
            connection.execute(
                """INSERT INTO runtime_mvp_views(user_id,environment,run_id,catalog_seq,document)
                   VALUES(%s,%s,%s,%s,%s)""", (*key, row["last_seq"], Jsonb(document)))

    def _mutate(self, owner, run_id, change):
        require_owner(owner)
        key = self._key(owner, run_id)
        with self._write() as connection:
            row = connection.execute(
                """SELECT document FROM runtime_mvp_views
                   WHERE user_id=%s AND environment=%s AND run_id=%s FOR UPDATE""", key).fetchone()
            if row is None:
                raise ActionRejected("VIEW_NOT_FOUND")
            document = bounded(change(json_copy(row["document"])))
            connection.execute(
                """UPDATE runtime_mvp_views SET document=%s,revision=revision+1
                   WHERE user_id=%s AND environment=%s AND run_id=%s""", (Jsonb(document), *key))

    def node(self, owner, run_id, node_id, status, summary=None):
        self._mutate(owner, run_id, lambda view: change_node(view, node_id, status, summary))

    def complete(self, owner, run_id, node_id, content):
        self._mutate(
            owner, run_id, lambda view: complete_node(view, node_id, content),
        )

    def output(self, owner, run_id, node_id, kind, content):
        self._mutate(owner, run_id, lambda view: put_output(view, node_id, kind, content))

    def view(self, owner, run_id):
        require_owner(owner)
        key = self._key(owner, run_id)
        with self._read(owner) as connection:
            row = connection.execute(
                """SELECT v.document,v.revision,r.document->>'status' AS lifecycle,
                          r.document->>'revision' AS lifecycle_revision
                   FROM runtime_mvp_views v JOIN runtime_runs r
                     USING(user_id,environment,run_id)
                   WHERE v.user_id=%s AND v.environment=%s AND v.run_id=%s""", key).fetchone()
            if row is None:
                raise ActionRejected("VIEW_NOT_FOUND")
            cards = connection.execute(
                """SELECT interaction_id,document FROM runtime_interactions
                   WHERE user_id=%s AND environment=%s AND run_id=%s
                   ORDER BY node_id,interaction_id""", key).fetchall()
        interactions = {}
        for card in cards:
            item = decode(card["document"])
            if (item.context.trusted_context != owner or item.key[0] != run_id
                    or card["interaction_id"] != item.interaction_id
                    or item.interaction_id in interactions):
                raise ActionRejected("PROJECTION_UNAVAILABLE")
            interactions[card["interaction_id"]] = item
        return project_view(row["document"], row["revision"], row["lifecycle"],
                            row["lifecycle_revision"], interactions)

    def runs(self, owner, *, after=None, limit=20):
        require_owner(owner)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ActionRejected("INVALID_VIEW_PAGE")
        if after is not None and (type(after) is not str or not re.fullmatch(r"mvp08:[1-9][0-9]{0,18}", after)):
            raise ActionRejected("INVALID_VIEW_CURSOR")
        owner_key = (owner.user_id, owner.environment)
        with self._read(owner) as connection:
            head = connection.execute(
                "SELECT last_seq FROM runtime_mvp_catalog WHERE user_id=%s AND environment=%s",
                owner_key).fetchone()
            maximum = head["last_seq"] if head else 0
            boundary = int(after.split(":")[1]) if after else maximum + 1
            if boundary > maximum + 1:
                raise ActionRejected("INVALID_VIEW_CURSOR")
            rows = connection.execute(
                """SELECT v.catalog_seq,v.run_id,v.document->>'definitionKey' AS definition_key,
                          v.document->>'title' AS title,v.document->>'createdAt' AS created_at,
                          r.document->>'status' AS lifecycle
                   FROM runtime_mvp_views v JOIN runtime_runs r USING(user_id,environment,run_id)
                   WHERE v.user_id=%s AND v.environment=%s AND v.catalog_seq<%s
                   ORDER BY v.catalog_seq DESC LIMIT %s""",
                (*owner_key, boundary, limit + 1)).fetchall()
        page = rows[:limit]
        return bounded({
            "items": [{"runId": row["run_id"], "definitionKey": row["definition_key"],
                       "title": row["title"], "lifecycle": row["lifecycle"],
                       "createdAt": row["created_at"]} for row in page],
            "nextCursor": f"mvp08:{page[-1]['catalog_seq']}" if len(rows) > limit else None,
        })
