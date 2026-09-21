"""Typed draft persistence ports and explicit memory/PostgreSQL adapters."""

import copy
import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import import_module
from typing import cast

from skillweave_contracts.asset_types import ASSET_KINDS, AssetKind, Environment, JsonObject

from .contracts import ManagedDraft, ManagementError, identifier
from .db_types import ConnectionFactory, DatabaseConnection, DatabaseRow
from .relations import (
    RELATION_DDL,
    DraftRelation,
    draft_relations,
    list_relations,
    replace_draft_relations,
)

DraftIdentity = tuple[str, AssetKind, str]
RelationSnapshotIdentity = tuple[str, AssetKind, str, int]

_DDL = (
    "CREATE TABLE IF NOT EXISTS a2flow_management_drafts "
    "(namespace TEXT NOT NULL, kind TEXT NOT NULL, asset_key TEXT NOT NULL, "
    "revision BIGINT NOT NULL CHECK(revision > 0), document BYTEA NOT NULL, "
    "digest TEXT NOT NULL, updated_by BIGINT NOT NULL, "
    "PRIMARY KEY(namespace,kind,asset_key))",
)


def _asset_kind(value: object) -> AssetKind:
    if type(value) is not str or value not in ASSET_KINDS:
        raise ManagementError("INVALID_DRAFT_ROW", 500)
    return cast(AssetKind, value)


def _text(value: object) -> str:
    if type(value) is not str:
        raise ManagementError("INVALID_DRAFT_ROW", 500)
    return value


def _positive_revision(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ManagementError("INVALID_DRAFT_ROW", 500)
    return value


def _user_id(value: object) -> int:
    if type(value) is not int:
        raise ManagementError("INVALID_DRAFT_ROW", 500)
    return value


def _document(value: object) -> JsonObject:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ManagementError("INVALID_DRAFT_ROW", 500)
    try:
        decoded = json.loads(bytes(value))
    except (TypeError, ValueError, UnicodeError):
        raise ManagementError("INVALID_DRAFT_ROW", 500) from None
    if type(decoded) is not dict:
        raise ManagementError("INVALID_DRAFT_ROW", 500)
    return cast(JsonObject, decoded)


def _stored_draft(
    kind: object,
    key: object,
    revision: object,
    document: object,
    expected_digest: object,
    updated_by: object,
) -> ManagedDraft:
    draft = ManagedDraft.create(
        _asset_kind(kind),
        _text(key),
        _positive_revision(revision),
        _document(document),
        _user_id(updated_by),
    )
    if draft.content_digest != _text(expected_digest):
        raise ManagementError("DRAFT_DIGEST_MISMATCH", 500)
    return draft


def _returned_revision(row: DatabaseRow | None, conflict_code: str) -> int:
    if row is None:
        raise ManagementError(conflict_code, 409)
    if len(row) != 1:
        raise ManagementError("INVALID_DRAFT_ROW", 500)
    return _positive_revision(row[0])


class DraftRepository(ABC):
    @property
    @abstractmethod
    def environment(self) -> Environment: ...

    @abstractmethod
    def get(self, namespace: str, kind: AssetKind, key: str) -> ManagedDraft | None: ...

    @abstractmethod
    def list(self, namespace: str, kind: AssetKind) -> tuple[ManagedDraft, ...]: ...

    @abstractmethod
    def save(self, namespace: str, draft: ManagedDraft, expected_revision: int) -> ManagedDraft: ...

    @abstractmethod
    def create(self, namespace: str, draft: ManagedDraft) -> ManagedDraft: ...

    @abstractmethod
    def list_relations(
        self,
        namespace: str,
        kind: AssetKind,
        key: str,
        revision: int | None = None,
    ) -> tuple[DraftRelation, ...]: ...

    @abstractmethod
    def commit_workspace(
        self,
        namespace: str,
        draft: ManagedDraft,
        expected_revision: int,
        workspace_namespace: str,
        workspace: ManagedDraft,
        expected_workspace_revision: int,
    ) -> tuple[ManagedDraft, ManagedDraft]: ...


class MemoryDraftRepository(DraftRepository):
    """Deterministic test/development adapter; never an implicit production fallback."""

    def __init__(self, environment: str) -> None:
        if environment not in {"PRT", "ONLINE"}:
            raise ManagementError("INVALID_TRUSTED_ENVIRONMENT")
        self._environment = cast(Environment, environment)
        self._rows: dict[DraftIdentity, ManagedDraft] = {}
        self._relations: dict[RelationSnapshotIdentity, tuple[DraftRelation, ...]] = {}

    @property
    def environment(self) -> Environment:
        return self._environment

    def get(self, namespace: str, kind: AssetKind, key: str) -> ManagedDraft | None:
        return self._rows.get((namespace, kind, key))

    def list(self, namespace: str, kind: AssetKind) -> tuple[ManagedDraft, ...]:
        return tuple(
            copy.deepcopy(value)
            for identity, value in sorted(self._rows.items())
            if identity[:2] == (namespace, kind)
        )

    def create(self, namespace: str, draft: ManagedDraft) -> ManagedDraft:
        identity = namespace, draft.kind, draft.key
        if identity in self._rows:
            raise ManagementError("DRAFT_REVISION_CONFLICT", 409)
        return self.save(namespace, draft, 0)

    def save(self, namespace: str, draft: ManagedDraft, expected_revision: int) -> ManagedDraft:
        identity = namespace, draft.kind, draft.key
        current = self._rows.get(identity)
        actual = 0 if current is None else current.revision
        if actual != expected_revision:
            raise ManagementError("DRAFT_REVISION_CONFLICT", 409)
        saved = ManagedDraft.create(
            draft.kind,
            draft.key,
            actual + 1,
            draft.document,
            draft.updated_by,
        )
        relations = draft_relations(namespace, saved, saved.revision)
        self._rows[identity] = copy.deepcopy(saved)
        self._relations[(*identity, saved.revision)] = relations
        return saved

    def list_relations(
        self,
        namespace: str,
        kind: AssetKind,
        key: str,
        revision: int | None = None,
    ) -> tuple[DraftRelation, ...]:
        selected_revision = revision
        if selected_revision is None:
            draft = self.get(namespace, kind, key)
            if draft is None:
                return ()
            selected_revision = draft.revision
        return copy.deepcopy(self._relations.get((namespace, kind, key, selected_revision), ()))

    def commit_workspace(
        self,
        namespace: str,
        draft: ManagedDraft,
        expected_revision: int,
        workspace_namespace: str,
        workspace: ManagedDraft,
        expected_workspace_revision: int,
    ) -> tuple[ManagedDraft, ManagedDraft]:
        current = self.get(namespace, draft.kind, draft.key)
        editing = self.get(workspace_namespace, draft.kind, draft.key)
        if editing is None or editing.revision != expected_workspace_revision:
            raise ManagementError("WORKSPACE_REVISION_CONFLICT", 409)
        if (current.revision if current else 0) != expected_revision:
            raise ManagementError("WORKSPACE_BASE_DRAFT_CONFLICT", 409)
        draft_relations(namespace, draft, expected_revision + 1)
        draft_relations(workspace_namespace, workspace, expected_workspace_revision + 1)
        return (
            self.save(namespace, draft, expected_revision),
            self.save(workspace_namespace, workspace, expected_workspace_revision),
        )


class PostgresDraftRepository(DraftRepository):
    """One environment/database binding; setup is an explicit operator action."""

    def __init__(
        self,
        conninfo: str,
        *,
        environment: str,
        database: str,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        if environment not in {"PRT", "ONLINE"}:
            raise ManagementError("INVALID_TRUSTED_ENVIRONMENT")
        if type(database) is not str or not database:
            raise ManagementError("EXACT_DATABASE_REQUIRED")
        self._environment = cast(Environment, environment)
        self.database = database
        self._conninfo = conninfo
        self._connect = connection_factory

    @property
    def environment(self) -> Environment:
        return self._environment

    @contextmanager
    def _connection(self) -> Iterator[DatabaseConnection]:
        connection: DatabaseConnection | None = None
        try:
            connect = self._connect
            if connect is None:
                connect = cast(ConnectionFactory, import_module("psycopg").connect)
            connection = connect(
                self._conninfo,
                autocommit=True,
                connect_timeout=5,
                options="-c statement_timeout=10000 -c lock_timeout=5000",
                application_name="a2flow-management",
            )
            row = connection.execute("SELECT current_database()").fetchone()
            if row is None or len(row) != 1 or row[0] != self.database:
                raise ManagementError("DATABASE_MISMATCH")
            environments = connection.execute(
                "SELECT environment FROM a2flow_asset_environment WHERE singleton=TRUE"
            ).fetchall()
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

    def setup(self) -> None:
        with self._connection() as connection, connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (78080302,))
            for statement in (*_DDL, *RELATION_DDL):
                connection.execute(statement)
            rows = connection.execute(
                "SELECT namespace,kind,asset_key,revision,document,digest,updated_by "
                "FROM a2flow_management_drafts FOR UPDATE"
            ).fetchall()
            for row in rows:
                if len(row) != 7:
                    raise ManagementError("INVALID_DRAFT_ROW", 500)
                namespace, kind, key, revision, document, expected_digest, updated_by = row
                draft = _stored_draft(
                    kind,
                    key,
                    revision,
                    document,
                    expected_digest,
                    updated_by,
                )
                replace_draft_relations(connection, _text(namespace), draft, draft.revision)

    def list_relations(
        self,
        namespace: str,
        kind: AssetKind,
        key: str,
        revision: int | None = None,
    ) -> tuple[DraftRelation, ...]:
        identifier(namespace, "INVALID_NAMESPACE")
        if revision is not None and (type(revision) is not int or revision < 1):
            raise ManagementError("INVALID_EXPECTED_REVISION")
        with self._connection() as connection:
            return list_relations(connection, namespace, kind, key, revision)

    def get(self, namespace: str, kind: AssetKind, key: str) -> ManagedDraft | None:
        identifier(namespace, "INVALID_NAMESPACE")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT revision,document,digest,updated_by "
                "FROM a2flow_management_drafts "
                "WHERE namespace=%s AND kind=%s AND asset_key=%s",
                (namespace, kind, key),
            ).fetchone()
        if row is None:
            return None
        if len(row) != 4:
            raise ManagementError("INVALID_DRAFT_ROW", 500)
        revision, document, expected_digest, updated_by = row
        return _stored_draft(kind, key, revision, document, expected_digest, updated_by)

    def list(self, namespace: str, kind: AssetKind) -> tuple[ManagedDraft, ...]:
        identifier(namespace, "INVALID_NAMESPACE")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT asset_key,revision,document,digest,updated_by "
                "FROM a2flow_management_drafts "
                "WHERE namespace=%s AND kind=%s ORDER BY asset_key",
                (namespace, kind),
            ).fetchall()
        result: list[ManagedDraft] = []
        for row in rows:
            if len(row) != 5:
                raise ManagementError("INVALID_DRAFT_ROW", 500)
            key, revision, document, expected_digest, updated_by = row
            result.append(
                _stored_draft(
                    kind,
                    key,
                    revision,
                    document,
                    expected_digest,
                    updated_by,
                )
            )
        return tuple(result)

    def create(self, namespace: str, draft: ManagedDraft) -> ManagedDraft:
        identifier(namespace, "INVALID_NAMESPACE")
        with self._connection() as connection, connection.transaction():
            lock = int.from_bytes(
                hashlib.sha256(namespace.encode()).digest()[:8],
                "big",
                signed=True,
            )
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
            published = connection.execute(
                "SELECT 1 FROM a2flow_asset_versions "
                "WHERE namespace=%s AND kind=%s AND asset_key=%s LIMIT 1",
                (namespace, draft.kind, draft.key),
            ).fetchone()
            if published is not None:
                raise ManagementError("ASSET_ALREADY_EXISTS", 409)
            revision = _returned_revision(
                self._insert(connection, namespace, draft),
                "DRAFT_REVISION_CONFLICT",
            )
            replace_draft_relations(connection, namespace, draft, revision)
            return ManagedDraft.create(
                draft.kind,
                draft.key,
                revision,
                draft.document,
                draft.updated_by,
            )

    @staticmethod
    def _insert(
        connection: DatabaseConnection, namespace: str, draft: ManagedDraft
    ) -> DatabaseRow | None:
        return connection.execute(
            "INSERT INTO a2flow_management_drafts "
            "(namespace,kind,asset_key,revision,document,digest,updated_by) "
            "VALUES(%s,%s,%s,1,%s,%s,%s) "
            "ON CONFLICT(namespace,kind,asset_key) DO NOTHING "
            "RETURNING revision",
            (
                namespace,
                draft.kind,
                draft.key,
                draft.data,
                draft.content_digest,
                draft.updated_by,
            ),
        ).fetchone()

    def save(self, namespace: str, draft: ManagedDraft, expected_revision: int) -> ManagedDraft:
        identifier(namespace, "INVALID_NAMESPACE")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ManagementError("INVALID_EXPECTED_REVISION")
        with self._connection() as connection, connection.transaction():
            if expected_revision == 0:
                row = self._insert(connection, namespace, draft)
            else:
                row = connection.execute(
                    "UPDATE a2flow_management_drafts SET revision=revision+1,"
                    "document=%s,digest=%s,updated_by=%s "
                    "WHERE namespace=%s AND kind=%s AND asset_key=%s "
                    "AND revision=%s RETURNING revision",
                    (
                        draft.data,
                        draft.content_digest,
                        draft.updated_by,
                        namespace,
                        draft.kind,
                        draft.key,
                        expected_revision,
                    ),
                ).fetchone()
            revision = _returned_revision(row, "DRAFT_REVISION_CONFLICT")
            replace_draft_relations(connection, namespace, draft, revision)
            return ManagedDraft.create(
                draft.kind,
                draft.key,
                revision,
                draft.document,
                draft.updated_by,
            )

    def commit_workspace(
        self,
        namespace: str,
        draft: ManagedDraft,
        expected_revision: int,
        workspace_namespace: str,
        workspace: ManagedDraft,
        expected_workspace_revision: int,
    ) -> tuple[ManagedDraft, ManagedDraft]:
        """Commit files and acknowledge the workspace in one PostgreSQL transaction."""
        identifier(namespace, "INVALID_NAMESPACE")
        identifier(workspace_namespace, "INVALID_NAMESPACE")
        for value in (expected_revision, expected_workspace_revision):
            if type(value) is not int or value < 0:
                raise ManagementError("INVALID_EXPECTED_REVISION")
        with self._connection() as connection, connection.transaction():
            editing_row = connection.execute(
                "UPDATE a2flow_management_drafts SET revision=revision+1,"
                "document=%s,digest=%s,updated_by=%s "
                "WHERE namespace=%s AND kind=%s AND asset_key=%s "
                "AND revision=%s RETURNING revision",
                (
                    workspace.data,
                    workspace.content_digest,
                    workspace.updated_by,
                    workspace_namespace,
                    workspace.kind,
                    workspace.key,
                    expected_workspace_revision,
                ),
            ).fetchone()
            editing_revision = _returned_revision(editing_row, "WORKSPACE_REVISION_CONFLICT")
            if expected_revision == 0:
                saved_row = self._insert(connection, namespace, draft)
            else:
                saved_row = connection.execute(
                    "UPDATE a2flow_management_drafts SET revision=revision+1,"
                    "document=%s,digest=%s,updated_by=%s "
                    "WHERE namespace=%s AND kind=%s AND asset_key=%s "
                    "AND revision=%s RETURNING revision",
                    (
                        draft.data,
                        draft.content_digest,
                        draft.updated_by,
                        namespace,
                        draft.kind,
                        draft.key,
                        expected_revision,
                    ),
                ).fetchone()
            saved_revision = _returned_revision(saved_row, "WORKSPACE_BASE_DRAFT_CONFLICT")
            replace_draft_relations(connection, namespace, draft, saved_revision)
            return (
                ManagedDraft.create(
                    draft.kind,
                    draft.key,
                    saved_revision,
                    draft.document,
                    draft.updated_by,
                ),
                ManagedDraft.create(
                    workspace.kind,
                    workspace.key,
                    editing_revision,
                    workspace.document,
                    workspace.updated_by,
                ),
            )
