"""Draft persistence ports and an explicit PostgreSQL adapter."""
from abc import ABC, abstractmethod
from contextlib import contextmanager
import copy

from .contracts import ManagedDraft, ManagementError, identifier

_DDL = (
    "CREATE TABLE IF NOT EXISTS a2flow_management_drafts "
    "(namespace TEXT NOT NULL, kind TEXT NOT NULL, asset_key TEXT NOT NULL, "
    "revision BIGINT NOT NULL CHECK(revision > 0), document BYTEA NOT NULL, "
    "digest TEXT NOT NULL, updated_by TEXT NOT NULL, "
    "PRIMARY KEY(namespace,kind,asset_key))",
)


class DraftRepository(ABC):
    @abstractmethod
    def get(self, namespace, kind, key): ...
    @abstractmethod
    def save(self, namespace, draft, expected_revision): ...


class MemoryDraftRepository(DraftRepository):
    """Deterministic test/development adapter; never an implicit production fallback."""
    def __init__(self):
        self._rows = {}

    def get(self, namespace, kind, key):
        return self._rows.get((namespace, kind, key))

    def save(self, namespace, draft, expected_revision):
        identity = namespace, draft.kind, draft.key
        current = self._rows.get(identity)
        actual = 0 if current is None else current.revision
        if actual != expected_revision:
            raise ManagementError("DRAFT_REVISION_CONFLICT", 409)
        saved = ManagedDraft.create(
            draft.kind, draft.key, actual + 1, draft.document, draft.updated_by)
        self._rows[identity] = copy.deepcopy(saved)
        return saved


class PostgresDraftRepository(DraftRepository):
    """One environment/database binding; setup is an explicit operator action."""
    def __init__(self, conninfo, *, environment, database, connection_factory=None):
        if environment not in {"PRT", "ONLINE"}:
            raise ManagementError("INVALID_TRUSTED_ENVIRONMENT")
        if type(database) is not str or not database:
            raise ManagementError("EXACT_DATABASE_REQUIRED")
        self.environment, self.database = environment, database
        self._conninfo, self._connect = conninfo, connection_factory

    @contextmanager
    def _connection(self):
        connection = None
        try:
            connect = self._connect
            if connect is None:
                import psycopg
                connect = psycopg.connect
            connection = connect(
                self._conninfo, autocommit=True, connect_timeout=5,
                options="-c statement_timeout=10000 -c lock_timeout=5000",
                application_name="a2flow-management")
            row = connection.execute("SELECT current_database()").fetchone()
            if not row or row[0] != self.database:
                raise ManagementError("DATABASE_MISMATCH")
            environments = connection.execute(
                "SELECT environment FROM a2flow_asset_environment "
                "WHERE singleton=TRUE").fetchall()
            if environments != [(self.environment,)]:
                raise ManagementError("DATABASE_ENVIRONMENT_MISMATCH")
            yield connection
        except ManagementError:
            raise
        except Exception:
            raise ManagementError("MANAGEMENT_DATABASE_ERROR", 503) from None
        finally:
            if connection is not None:
                connection.close()

    def setup(self):
        with self._connection() as connection:
            with connection.transaction():
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (78080302,))
                for statement in _DDL:
                    connection.execute(statement)

    def get(self, namespace, kind, key):
        identifier(namespace, "INVALID_NAMESPACE")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT revision,document,digest,updated_by "
                "FROM a2flow_management_drafts "
                "WHERE namespace=%s AND kind=%s AND asset_key=%s",
                (namespace, kind, key)).fetchone()
        if row is None:
            return None
        revision, document, digest, updated_by = row
        draft = ManagedDraft.create(kind, key, revision,
                                    __import__("json").loads(bytes(document)), updated_by)
        if draft.content_digest != digest:
            raise ManagementError("DRAFT_DIGEST_MISMATCH", 500)
        return draft

    def save(self, namespace, draft, expected_revision):
        identifier(namespace, "INVALID_NAMESPACE")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ManagementError("INVALID_EXPECTED_REVISION")
        with self._connection() as connection:
            with connection.transaction():
                if expected_revision == 0:
                    row = connection.execute(
                        "INSERT INTO a2flow_management_drafts "
                        "(namespace,kind,asset_key,revision,document,digest,updated_by) "
                        "VALUES(%s,%s,%s,1,%s,%s,%s) "
                        "ON CONFLICT(namespace,kind,asset_key) DO NOTHING "
                        "RETURNING revision",
                        (namespace, draft.kind, draft.key, draft.data,
                         draft.content_digest, draft.updated_by)).fetchone()
                else:
                    row = connection.execute(
                        "UPDATE a2flow_management_drafts SET revision=revision+1,"
                        "document=%s,digest=%s,updated_by=%s "
                        "WHERE namespace=%s AND kind=%s AND asset_key=%s "
                        "AND revision=%s RETURNING revision",
                        (draft.data, draft.content_digest, draft.updated_by,
                         namespace, draft.kind, draft.key,
                         expected_revision)).fetchone()
                if row is None:
                    raise ManagementError("DRAFT_REVISION_CONFLICT", 409)
                return ManagedDraft.create(
                    draft.kind, draft.key, row[0], draft.document, draft.updated_by)
