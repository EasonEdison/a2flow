"""PostgreSQL Action repository with dedicated session-lock connections.

A lock scope is NOT a transaction. Saves commit before external execution.
No pool, reconnection, lease takeover, scheduler or side-effect exactly-once claim.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from threading import local

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import ActionRejected
from .serialization import decode, encode, request_document


DDL = (
    """CREATE TABLE IF NOT EXISTS runtime_interactions (
        user_id BIGINT NOT NULL, environment TEXT NOT NULL,
        run_id TEXT NOT NULL, node_id TEXT NOT NULL, interaction_id TEXT NOT NULL,
        document JSONB NOT NULL,
        PRIMARY KEY (user_id, environment, run_id, node_id, interaction_id)
    )""",
    """CREATE TABLE IF NOT EXISTS runtime_controls (
        user_id BIGINT NOT NULL, environment TEXT NOT NULL,
        run_id TEXT NOT NULL, node_id TEXT NOT NULL, interaction_id TEXT NOT NULL,
        control_request_id TEXT NOT NULL, request JSONB NOT NULL, document JSONB NOT NULL,
        PRIMARY KEY (user_id, environment, run_id, node_id, interaction_id, control_request_id),
        FOREIGN KEY (user_id, environment, run_id, node_id, interaction_id)
            REFERENCES runtime_interactions
    )""",
)


def lock_key(owner, run_id, kind):
    value = json.dumps([owner.user_id, owner.environment, run_id, kind], separators=(",", ":"))
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big", signed=True)


@dataclass
class _Scope:
    owner: object
    run_id: str
    kind: str
    connection: object
    key: int
    failed: bool = False


class PostgresInteractionRepository:
    """One new connection per scope; instances may be shared by SDK worker threads."""

    def __init__(self, conninfo, *, connection_factory=psycopg.connect):
        self._conninfo = conninfo
        self._connect = connection_factory
        self._local = local()

    def _stack(self):
        if not hasattr(self._local, "scopes"):
            self._local.scopes = []
        return self._local.scopes

    def _connection(self):
        try:
            return self._connect(
                self._conninfo, autocommit=True, row_factory=dict_row, connect_timeout=5,
                options="-c lock_timeout=5000 -c statement_timeout=10000",
                application_name="a2flow-runtime03",
            )
        except Exception:
            raise ActionRejected("REPOSITORY_CONNECTION_FAILED") from None

    def setup(self):
        """Explicit migration/setup step; never performed implicitly by request paths."""
        connection = self._connection()
        try:
            with connection.transaction():
                for statement in DDL:
                    connection.execute(statement)
        except Exception:
            raise ActionRejected("REPOSITORY_SETUP_FAILED") from None
        finally:
            connection.close()

    def check_scope(self):
        """Detect loss on ALL owning connections; not fencing of in-flight side effects."""
        stack = self._stack()
        if not stack:
            raise ActionRejected("REPOSITORY_SCOPE_REQUIRED")
        for scope in stack:
            try:
                if scope.failed or scope.connection.closed or scope.connection.broken:
                    raise RuntimeError()
                unsigned = scope.key & ((1 << 64) - 1)
                row = scope.connection.execute(
                    """SELECT EXISTS (
                        SELECT 1 FROM pg_locks
                        WHERE locktype = 'advisory' AND pid = pg_backend_pid()
                          AND classid = %s::oid AND objid = %s::oid AND objsubid = 1 AND granted
                    ) AS held""", (unsigned >> 32, unsigned & 0xffffffff),
                ).fetchone()
                if not row["held"]:
                    raise RuntimeError()
            except Exception:
                scope.failed = True
                raise ActionRejected("LOCK_CONNECTION_LOST") from None

    @contextmanager
    def _scope(self, owner, run_id, kind):
        stack = self._stack()
        if stack:
            self.check_scope()
        if any(s.kind == kind for s in stack):
            raise ActionRejected("NESTED_REPOSITORY_SCOPE")
        connection = self._connection()
        scope = _Scope(owner, run_id, kind, connection, lock_key(owner, run_id, kind))
        acquired = False
        try:
            try:
                connection.execute("SELECT pg_advisory_lock(%s)", (scope.key,))
                acquired = True
            except Exception:
                raise ActionRejected("LOCK_ACQUISITION_FAILED") from None
            stack.append(scope)
            try:
                self.check_scope()
                yield
                self.check_scope()
            finally:
                stack.pop()
        finally:
            try:
                if acquired and not scope.failed and not connection.closed and not connection.broken:
                    connection.execute("SELECT pg_advisory_unlock(%s)", (scope.key,))
            except Exception:
                # A failed unlock still closes the dedicated session. Never return it to a pool.
                pass
            finally:
                connection.close()

    def scope(self, owner, run_id):
        return self._scope(owner, run_id, "admission")

    def continuation_scope(self, owner, run_id):
        return self._scope(owner, run_id, "continuation")

    def _current(self, owner, run_id, *, write=False):
        self.check_scope()
        scope = self._stack()[-1]
        if scope.owner != owner or scope.run_id != run_id or (write and scope.kind != "admission"):
            raise ActionRejected("REPOSITORY_SCOPE_MISMATCH")
        return scope

    def _execute(self, scope, statement, params):
        try:
            return scope.connection.execute(statement, params)
        except Exception:
            scope.failed = True
            raise ActionRejected("REPOSITORY_OPERATION_UNCONFIRMED") from None

    @staticmethod
    def _identity(owner, key):
        return (owner.user_id, owner.environment, *key)

    @staticmethod
    def _decode_row(row, owner, key=None):
        item = decode(row["document"])
        if item.context.trusted_context != owner or (key is not None and item.key != key):
            raise ActionRejected("INVALID_STORED_RECORD")
        return item

    def get(self, key, owner):
        scope = self._current(owner, key[0])
        row = self._execute(scope, """SELECT document FROM runtime_interactions
            WHERE user_id=%s AND environment=%s AND run_id=%s AND node_id=%s
              AND interaction_id=%s""", self._identity(owner, key)).fetchone()
        return None if row is None else self._decode_row(row, owner, key)

    def for_run(self, owner, run_id):
        scope = self._current(owner, run_id)
        rows = self._execute(scope, """SELECT document FROM runtime_interactions
            WHERE user_id=%s AND environment=%s AND run_id=%s
            ORDER BY node_id, interaction_id""", (owner.user_id, owner.environment, run_id)).fetchall()
        items = tuple(self._decode_row(row, owner) for row in rows)
        if any(item.key[0] != run_id for item in items):
            raise ActionRejected("INVALID_STORED_RECORD")
        return items

    def for_node(self, owner, run_id, node_id):
        return tuple(item for item in self.for_run(owner, run_id) if item.key[1] == node_id)

    def save(self, interaction):
        owner = interaction.context.trusted_context
        scope = self._current(owner, interaction.key[0], write=True)
        document = encode(interaction)
        old = self.get(interaction.key, owner)
        if old is not None:
            old_requests = {a.request.control_request_id: a.request for a in old.attempts}
            new_requests = {a.request.control_request_id: a.request for a in interaction.attempts}
            if any(new_requests.get(key) != value for key, value in old_requests.items()):
                raise ActionRejected("CONTROL_HISTORY_CONFLICT")
        identity = self._identity(owner, interaction.key)
        try:
            with scope.connection.transaction():
                self._execute(scope, """INSERT INTO runtime_interactions
                    (user_id, environment, run_id, node_id, interaction_id, document)
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id, environment, run_id, node_id, interaction_id)
                    DO UPDATE SET document=EXCLUDED.document""", (*identity, Jsonb(document)))
                for attempt, stored in zip(interaction.attempts, document["attempts"]):
                    row = self._execute(scope, """INSERT INTO runtime_controls
                        (user_id,environment,run_id,node_id,interaction_id,
                         control_request_id,request,document)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (user_id,environment,run_id,node_id,interaction_id,control_request_id)
                        DO UPDATE SET document=EXCLUDED.document
                        WHERE runtime_controls.request=EXCLUDED.request
                        RETURNING control_request_id""", (
                            *identity, attempt.request.control_request_id,
                            Jsonb(request_document(attempt.request)), Jsonb({"schemaVersion": 1, **stored}),
                        )).fetchone()
                    if row is None:
                        raise ActionRejected("CONTROL_REQUEST_CONFLICT")
        except ActionRejected:
            raise
        except Exception:
            scope.failed = True
            raise ActionRejected("REPOSITORY_COMMIT_UNCONFIRMED") from None
        self.check_scope()
