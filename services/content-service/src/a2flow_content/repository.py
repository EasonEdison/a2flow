"""PostgreSQL-only persistence with owner isolation, CAS and request receipts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from importlib import import_module
from importlib.resources import files
from typing import Protocol, TypeAlias, cast
from uuid import UUID, uuid4

from .errors import ContentError
from .models import (
    ArtifactKind,
    ArtifactOrigin,
    ArtifactRecord,
    ConfirmationRecord,
    ConfirmationSelection,
    ConfirmManuscriptCommand,
    ConfirmReadingCommand,
    ConfirmTopicCommand,
    DecisionType,
    Environment,
    InputReference,
    JsonObject,
    JsonValue,
    ListProjectsQuery,
    Manuscript,
    ManuscriptSelection,
    OutputFormat,
    ProjectPage,
    ProjectRecord,
    ReadingBrief,
    ReadingSelection,
    ReferenceKind,
    SaveArtifactCommand,
    SaveSourceCommand,
    SourceRecord,
    TopicPlan,
    TopicSelection,
    TrustedContext,
    body_from_json,
    body_json,
    canonical_json,
    payload_digest,
    reference_json,
)

Row: TypeAlias = tuple[object, ...]
Params: TypeAlias = tuple[object, ...]


class Result(Protocol):
    def fetchone(self) -> Row | None: ...

    def fetchall(self) -> list[Row]: ...


class Connection(Protocol):
    def execute(self, query: str, params: Params = ()) -> Result: ...

    def transaction(self) -> AbstractContextManager[object]: ...

    def close(self) -> None: ...


Connect: TypeAlias = Callable[..., Connection]

PROJECT_COLUMNS = (
    "id,title,audience,output_format,current_source_id,current_selection_id,"
    "current_manuscript_id,revision,created_at,updated_at"
)
SOURCE_COLUMNS = "id,project_id,revision,title,source_url,body,digest,created_at"
ARTIFACT_COLUMNS = "id,project_id,kind,revision,body_json,input_refs,origin,created_at"
CONFIRMATION_COLUMNS = "id,project_id,artifact_id,decision_type,selection_json,created_at"


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if type(value) is str:
        try:
            return UUID(value)
        except ValueError:
            pass
    raise ContentError("INVALID_DATABASE_ROW", 500)


def _optional_uuid(value: object) -> UUID | None:
    return None if value is None else _uuid(value)


def _str(value: object) -> str:
    if type(value) is not str:
        raise ContentError("INVALID_DATABASE_ROW", 500)
    return value


def _optional_str(value: object) -> str | None:
    return None if value is None else _str(value)


def _int(value: object) -> int:
    if type(value) is not int:
        raise ContentError("INVALID_DATABASE_ROW", 500)
    return value


def _time(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ContentError("INVALID_DATABASE_ROW", 500)
    return value


def _json(value: object) -> object:
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return json.loads(bytes(value))
        except (TypeError, ValueError, UnicodeError):
            raise ContentError("INVALID_DATABASE_ROW", 500) from None
    if type(value) is str:
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            raise ContentError("INVALID_DATABASE_ROW", 500) from None
    return value


def _project(row: Row | None) -> ProjectRecord:
    if row is None:
        raise ContentError("CONTENT_NOT_FOUND", 404)
    if len(row) != 10:
        raise ContentError("INVALID_DATABASE_ROW", 500)
    try:
        output_format = OutputFormat(_str(row[3]))
    except (TypeError, ValueError):
        raise ContentError("INVALID_DATABASE_ROW", 500) from None
    return ProjectRecord(
        _uuid(row[0]),
        _str(row[1]),
        _str(row[2]),
        output_format,
        _optional_uuid(row[4]),
        _optional_uuid(row[5]),
        _optional_uuid(row[6]),
        _int(row[7]),
        _time(row[8]),
        _time(row[9]),
    )


def _source(row: Row | None) -> SourceRecord:
    if row is None:
        raise ContentError("CONTENT_NOT_FOUND", 404)
    if len(row) != 8:
        raise ContentError("INVALID_DATABASE_ROW", 500)
    return SourceRecord(
        _uuid(row[0]),
        _uuid(row[1]),
        _int(row[2]),
        _str(row[3]),
        _optional_str(row[4]),
        _str(row[5]),
        _str(row[6]),
        _time(row[7]),
    )


def _references(value: object) -> tuple[InputReference, ...]:
    raw = _json(value)
    if type(raw) is not list:
        raise ContentError("INVALID_DATABASE_ROW", 500)
    result: list[InputReference] = []
    for item in cast(list[object], raw):
        if type(item) is not dict:
            raise ContentError("INVALID_DATABASE_ROW", 500)
        mapping = cast(dict[str, object], item)
        try:
            result.append(
                InputReference(
                    ReferenceKind(_str(mapping.get("kind"))),
                    _uuid(mapping.get("id")),
                    _int(mapping.get("revision")),
                )
            )
        except (TypeError, ValueError):
            raise ContentError("INVALID_DATABASE_ROW", 500) from None
    return tuple(result)


def _artifact(row: Row | None) -> ArtifactRecord:
    if row is None:
        raise ContentError("CONTENT_NOT_FOUND", 404)
    if len(row) != 8:
        raise ContentError("INVALID_DATABASE_ROW", 500)
    try:
        kind = ArtifactKind(_str(row[2]))
        origin = ArtifactOrigin(_str(row[6]))
    except (TypeError, ValueError):
        raise ContentError("INVALID_DATABASE_ROW", 500) from None
    body = body_from_json(_json(row[4]))
    if {
        ArtifactKind.READING_BRIEF: ReadingBrief,
        ArtifactKind.TOPIC_PLAN: TopicPlan,
        ArtifactKind.MANUSCRIPT: Manuscript,
    }[kind] is not type(body):
        raise ContentError("INVALID_DATABASE_ROW", 500)
    return ArtifactRecord(
        _uuid(row[0]),
        _uuid(row[1]),
        kind,
        _int(row[3]),
        body,
        _references(row[5]),
        origin,
        _time(row[7]),
    )


def _confirmation(row: Row | None) -> ConfirmationRecord:
    if row is None:
        raise ContentError("CONTENT_NOT_FOUND", 404)
    if len(row) != 6:
        raise ContentError("INVALID_DATABASE_ROW", 500)
    try:
        decision = DecisionType(_str(row[3]))
    except (TypeError, ValueError):
        raise ContentError("INVALID_DATABASE_ROW", 500) from None
    raw = _json(row[4])
    if type(raw) is not dict:
        raise ContentError("INVALID_DATABASE_ROW", 500)
    value = cast(dict[str, object], raw)
    if decision is DecisionType.READING:
        selected = value.get("selectedPointIds")
        if type(selected) is not list or not all(type(item) is str for item in selected):
            raise ContentError("INVALID_DATABASE_ROW", 500)
        selection: ConfirmationSelection = ReadingSelection(
            tuple(cast(list[str], selected)), _optional_str(value.get("userNotes"))
        )
    elif decision is DecisionType.TOPIC:
        selection = TopicSelection(
            _str(value.get("topicId")),
            _str(value.get("editedTitle")),
            _str(value.get("editedAngle")),
        )
    else:
        selection = ManuscriptSelection(_int(value.get("artifactRevision")))
    return ConfirmationRecord(
        _uuid(row[0]), _uuid(row[1]), _uuid(row[2]), decision, selection, _time(row[5])
    )


class PostgresContentRepository:
    """One configured environment/database; no request-controlled DSN or fallback."""

    def __init__(
        self,
        conninfo: str,
        *,
        environment: Environment,
        database: str,
        connection_factory: Connect | None = None,
    ) -> None:
        if not conninfo or not database:
            raise ContentError("DATABASE_CONFIGURATION_REQUIRED", 500)
        if not isinstance(environment, Environment):
            raise ContentError("INVALID_SERVICE_ENVIRONMENT", 500)
        self.environment = environment
        self.database = database
        self._conninfo = conninfo
        self._connect = connection_factory

    def _context(self, context: TrustedContext) -> None:
        if context.environment is not self.environment:
            raise ContentError("ENVIRONMENT_MISMATCH", 403)

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        connection: Connection | None = None
        try:
            connect = self._connect
            if connect is None:
                connect = cast(Connect, import_module("psycopg").connect)
            connection = connect(
                self._conninfo,
                autocommit=True,
                connect_timeout=5,
                options="-c statement_timeout=10000 -c lock_timeout=5000",
                application_name="a2flow-content-service",
            )
            row = connection.execute("SELECT current_database()").fetchone()
            if row is None or len(row) != 1 or row[0] != self.database:
                raise ContentError("DATABASE_MISMATCH", 500)
            yield connection
        except ContentError:
            raise
        except Exception:
            raise ContentError("CONTENT_DATABASE_ERROR", 503) from None
        finally:
            if connection is not None:
                connection.close()

    def setup(self) -> None:
        ddl = (
            files("a2flow_content")
            .joinpath("migrations", "001_content_schema.sql")
            .read_text(encoding="utf-8")
        )
        with self._connection() as connection, connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(%s)", (78080923,))
            connection.execute(ddl)

    def check_ready(self) -> None:
        """Read-only startup gate; schema creation remains an explicit action."""
        checks = (
            "SELECT id,user_id,title,audience,output_format,current_source_id,"
            "current_selection_id,current_manuscript_id,revision,created_at,updated_at "
            "FROM a2flow_content.content_project LIMIT 0",
            "SELECT id,project_id,user_id,revision,title,source_url,body,digest,created_at "
            "FROM a2flow_content.content_source LIMIT 0",
            "SELECT id,project_id,user_id,kind,revision,body_json,body_markdown,input_refs,"
            "origin,created_at FROM a2flow_content.content_artifact LIMIT 0",
            "SELECT id,project_id,user_id,artifact_id,decision_type,selection_json,created_at "
            "FROM a2flow_content.content_confirmation LIMIT 0",
            "SELECT user_id,operation,request_id,payload_digest,result_ref,result_json,created_at "
            "FROM a2flow_content.content_request_receipt LIMIT 0",
        )
        with self._connection() as connection, connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            for query in checks:
                connection.execute(query)

    @staticmethod
    def _lock_receipt(
        connection: Connection,
        context: TrustedContext,
        operation: str,
        digest: str,
    ) -> tuple[UUID, object | None] | None:
        scope = f"{context.user_id}\0{operation}\0{context.request_id}".encode()
        key = int.from_bytes(hashlib.sha256(scope).digest()[:8], "big", signed=True)
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
        row = connection.execute(
            "SELECT payload_digest,result_ref,result_json "
            "FROM a2flow_content.content_request_receipt "
            "WHERE user_id=%s AND operation=%s AND request_id=%s FOR UPDATE",
            (context.user_id, operation, context.request_id),
        ).fetchone()
        if row is None:
            return None
        if len(row) != 3 or row[0] != digest:
            raise ContentError("IDEMPOTENCY_CONFLICT", 409)
        return _uuid(row[1]), _json(row[2]) if row[2] is not None else None

    @staticmethod
    def _receipt(
        connection: Connection,
        context: TrustedContext,
        operation: str,
        digest: str,
        result_ref: UUID,
        result_json: JsonObject | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO a2flow_content.content_request_receipt"
            "(user_id,operation,request_id,payload_digest,result_ref,result_json) "
            "VALUES(%s,%s,%s,%s,%s,%s::jsonb)",
            (
                context.user_id,
                operation,
                context.request_id,
                digest,
                result_ref,
                None if result_json is None else canonical_json(result_json).decode(),
            ),
        )

    @staticmethod
    def _owned_project(
        connection: Connection, context: TrustedContext, project_id: UUID
    ) -> ProjectRecord:
        row = connection.execute(
            f"SELECT {PROJECT_COLUMNS} FROM a2flow_content.content_project "
            "WHERE id=%s AND user_id=%s FOR UPDATE",
            (project_id, context.user_id),
        ).fetchone()
        return _project(row)

    @staticmethod
    def _source_row(
        connection: Connection, context: TrustedContext, source_id: UUID
    ) -> SourceRecord:
        return _source(
            connection.execute(
                f"SELECT {SOURCE_COLUMNS} FROM a2flow_content.content_source "
                "WHERE id=%s AND user_id=%s",
                (source_id, context.user_id),
            ).fetchone()
        )

    @staticmethod
    def _artifact_row(
        connection: Connection, context: TrustedContext, artifact_id: UUID
    ) -> ArtifactRecord:
        return _artifact(
            connection.execute(
                f"SELECT {ARTIFACT_COLUMNS} FROM a2flow_content.content_artifact "
                "WHERE id=%s AND user_id=%s",
                (artifact_id, context.user_id),
            ).fetchone()
        )

    @staticmethod
    def _confirmation_row(
        connection: Connection, context: TrustedContext, confirmation_id: UUID
    ) -> ConfirmationRecord:
        return _confirmation(
            connection.execute(
                f"SELECT {CONFIRMATION_COLUMNS} FROM a2flow_content.content_confirmation "
                "WHERE id=%s AND user_id=%s",
                (confirmation_id, context.user_id),
            ).fetchone()
        )

    def create_project(
        self, context: TrustedContext, title: str, audience: str, output_format: str
    ) -> ProjectRecord:
        self._context(context)
        payload: JsonObject = {
            "title": title,
            "audience": audience,
            "outputFormat": output_format,
        }
        digest = payload_digest(payload)
        with self._connection() as connection, connection.transaction():
            replay = self._lock_receipt(connection, context, "content.project.create", digest)
            if replay is not None:
                replay_ref, snapshot = replay
                if type(snapshot) is not dict:
                    raise ContentError("INVALID_DATABASE_ROW", 500)
                saved = cast(dict[str, object], snapshot)
                if _uuid(saved.get("id")) != replay_ref:
                    raise ContentError("INVALID_DATABASE_ROW", 500)
                try:
                    return ProjectRecord(
                        replay_ref,
                        _str(saved.get("title")),
                        _str(saved.get("audience")),
                        OutputFormat(_str(saved.get("outputFormat"))),
                        _optional_uuid(saved.get("currentSourceId")),
                        _optional_uuid(saved.get("currentSelectionId")),
                        _optional_uuid(saved.get("currentManuscriptId")),
                        _int(saved.get("revision")),
                        datetime.fromisoformat(_str(saved.get("createdAt"))),
                        datetime.fromisoformat(_str(saved.get("updatedAt"))),
                    )
                except (TypeError, ValueError):
                    raise ContentError("INVALID_DATABASE_ROW", 500) from None
            project_id = uuid4()
            row = connection.execute(
                "INSERT INTO a2flow_content.content_project"
                "(id,user_id,title,audience,output_format,revision) VALUES(%s,%s,%s,%s,%s,1) "
                f"RETURNING {PROJECT_COLUMNS}",
                (project_id, context.user_id, title, audience, output_format),
            ).fetchone()
            record = _project(row)
            self._receipt(
                connection,
                context,
                "content.project.create",
                digest,
                project_id,
                {
                    "id": str(record.id),
                    "title": record.title,
                    "audience": record.audience,
                    "outputFormat": record.output_format.value,
                    "currentSourceId": None,
                    "currentSelectionId": None,
                    "currentManuscriptId": None,
                    "revision": record.revision,
                    "createdAt": record.created_at.isoformat(),
                    "updatedAt": record.updated_at.isoformat(),
                },
            )
            return record

    def list_projects(self, context: TrustedContext, query: ListProjectsQuery) -> ProjectPage:
        self._context(context)
        offset = (query.page - 1) * query.page_size
        with self._connection() as connection, connection.transaction():
            total_row = connection.execute(
                "SELECT count(*) FROM a2flow_content.content_project WHERE user_id=%s",
                (context.user_id,),
            ).fetchone()
            if total_row is None or len(total_row) != 1:
                raise ContentError("INVALID_DATABASE_ROW", 500)
            rows = connection.execute(
                f"SELECT {PROJECT_COLUMNS} FROM a2flow_content.content_project "
                "WHERE user_id=%s ORDER BY updated_at DESC,id DESC LIMIT %s OFFSET %s",
                (context.user_id, query.page_size, offset),
            ).fetchall()
            return ProjectPage(
                tuple(_project(row) for row in rows),
                _int(total_row[0]),
                query.page,
                query.page_size,
            )

    def get_project(self, context: TrustedContext, project_id: UUID) -> ProjectRecord:
        self._context(context)
        with self._connection() as connection:
            return _project(
                connection.execute(
                    f"SELECT {PROJECT_COLUMNS} FROM a2flow_content.content_project "
                    "WHERE id=%s AND user_id=%s",
                    (project_id, context.user_id),
                ).fetchone()
            )

    def save_source(self, context: TrustedContext, command: SaveSourceCommand) -> SourceRecord:
        self._context(context)
        payload: JsonObject = {
            "projectId": str(command.project_id),
            "title": command.title,
            "body": command.body,
            "sourceUrl": command.source_url,
        }
        digest = payload_digest(payload)
        with self._connection() as connection, connection.transaction():
            replay = self._lock_receipt(connection, context, "content.source.save", digest)
            if replay is not None:
                return self._source_row(connection, context, replay[0])
            self._owned_project(connection, context, command.project_id)
            next_row = connection.execute(
                "SELECT coalesce(max(revision),0)+1 FROM a2flow_content.content_source "
                "WHERE project_id=%s",
                (command.project_id,),
            ).fetchone()
            if next_row is None or len(next_row) != 1:
                raise ContentError("INVALID_DATABASE_ROW", 500)
            source_id = uuid4()
            body_digest = "sha256:" + hashlib.sha256(command.body.encode()).hexdigest()
            row = connection.execute(
                "INSERT INTO a2flow_content.content_source"
                "(id,project_id,user_id,revision,title,source_url,body,digest) "
                f"VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {SOURCE_COLUMNS}",
                (
                    source_id,
                    command.project_id,
                    context.user_id,
                    _int(next_row[0]),
                    command.title,
                    command.source_url,
                    command.body,
                    body_digest,
                ),
            ).fetchone()
            connection.execute(
                "UPDATE a2flow_content.content_project SET current_source_id=%s,"
                "revision=revision+1,updated_at=CURRENT_TIMESTAMP "
                "WHERE id=%s AND user_id=%s",
                (source_id, command.project_id, context.user_id),
            )
            self._receipt(connection, context, "content.source.save", digest, source_id)
            return _source(row)

    def get_source(self, context: TrustedContext, source_id: UUID) -> SourceRecord:
        self._context(context)
        with self._connection() as connection:
            return self._source_row(connection, context, source_id)

    def _validated_inputs(
        self,
        connection: Connection,
        context: TrustedContext,
        command: SaveArtifactCommand,
    ) -> tuple[dict[UUID, SourceRecord], dict[UUID, ArtifactRecord]]:
        sources: dict[UUID, SourceRecord] = {}
        artifacts: dict[UUID, ArtifactRecord] = {}
        for reference in command.input_refs:
            if reference.kind is ReferenceKind.SOURCE:
                source_item = self._source_row(connection, context, reference.id)
                if (
                    source_item.project_id != command.project_id
                    or source_item.revision != reference.revision
                ):
                    raise ContentError("INPUT_REFERENCE_NOT_FOUND", 404)
                sources[source_item.id] = source_item
            else:
                artifact_item = self._artifact_row(connection, context, reference.id)
                if (
                    artifact_item.project_id != command.project_id
                    or artifact_item.revision != reference.revision
                ):
                    raise ContentError("INPUT_REFERENCE_NOT_FOUND", 404)
                artifacts[artifact_item.id] = artifact_item
        return sources, artifacts

    @staticmethod
    def _validate_evidence(
        command: SaveArtifactCommand,
        sources: dict[UUID, SourceRecord],
        artifacts: dict[UUID, ArtifactRecord],
    ) -> None:
        if isinstance(command.body, ReadingBrief):
            if not sources:
                raise ContentError("SOURCE_REFERENCE_REQUIRED")
            for point in command.body.points:
                if not point.model_suggestion and not any(
                    point.evidence_quote is not None and point.evidence_quote in item.body
                    for item in sources.values()
                ):
                    raise ContentError("EVIDENCE_NOT_IN_REFERENCED_SOURCE")
        elif isinstance(command.body, TopicPlan):
            available = {
                point.id
                for item in artifacts.values()
                if isinstance(item.body, ReadingBrief)
                for point in item.body.points
            }
            if not available:
                raise ContentError("READING_BRIEF_REFERENCE_REQUIRED")
            for topic in command.body.topics:
                if not topic.source_point_ids or not set(topic.source_point_ids) <= available:
                    raise ContentError("UNKNOWN_SOURCE_POINT")
        else:
            allowed = {(item.kind, item.id, item.revision) for item in command.input_refs}
            for citation in command.body.citations:
                key = (citation.reference_kind, citation.reference_id, citation.revision)
                if key not in allowed:
                    raise ContentError("CITATION_NOT_IN_INPUT_REFERENCES")

    def save_artifact(
        self, context: TrustedContext, command: SaveArtifactCommand
    ) -> ArtifactRecord:
        self._context(context)
        body = body_json(command.body)
        refs: list[JsonValue] = [reference_json(item) for item in command.input_refs]
        payload: JsonObject = {
            "projectId": str(command.project_id),
            "kind": command.kind.value,
            "body": body,
            "inputRefs": refs,
            "origin": command.origin.value,
        }
        digest = payload_digest(payload)
        with self._connection() as connection, connection.transaction():
            replay = self._lock_receipt(connection, context, "content.artifact.save", digest)
            if replay is not None:
                return self._artifact_row(connection, context, replay[0])
            self._owned_project(connection, context, command.project_id)
            sources, artifacts = self._validated_inputs(connection, context, command)
            self._validate_evidence(command, sources, artifacts)
            next_row = connection.execute(
                "SELECT coalesce(max(revision),0)+1 FROM a2flow_content.content_artifact "
                "WHERE project_id=%s AND kind=%s",
                (command.project_id, command.kind.value),
            ).fetchone()
            if next_row is None or len(next_row) != 1:
                raise ContentError("INVALID_DATABASE_ROW", 500)
            artifact_id = uuid4()
            row = connection.execute(
                "INSERT INTO a2flow_content.content_artifact"
                "(id,project_id,user_id,kind,revision,body_json,body_markdown,input_refs,origin) "
                f"VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s) RETURNING {ARTIFACT_COLUMNS}",
                (
                    artifact_id,
                    command.project_id,
                    context.user_id,
                    command.kind.value,
                    _int(next_row[0]),
                    canonical_json(body).decode(),
                    command.body.body_markdown if isinstance(command.body, Manuscript) else "",
                    canonical_json(refs).decode(),
                    command.origin.value,
                ),
            ).fetchone()
            self._receipt(connection, context, "content.artifact.save", digest, artifact_id)
            return _artifact(row)

    def get_artifact(self, context: TrustedContext, artifact_id: UUID) -> ArtifactRecord:
        self._context(context)
        with self._connection() as connection:
            return self._artifact_row(connection, context, artifact_id)

    def get_confirmation(
        self, context: TrustedContext, confirmation_id: UUID
    ) -> ConfirmationRecord:
        self._context(context)
        with self._connection() as connection:
            return self._confirmation_row(connection, context, confirmation_id)

    def _confirm(
        self,
        context: TrustedContext,
        *,
        operation: str,
        project_id: UUID,
        artifact_id: UUID,
        decision: DecisionType,
        selection: JsonObject,
    ) -> ConfirmationRecord:
        digest = payload_digest(
            {
                "projectId": str(project_id),
                "artifactId": str(artifact_id),
                "selection": selection,
            }
        )
        with self._connection() as connection, connection.transaction():
            replay = self._lock_receipt(connection, context, operation, digest)
            if replay is not None:
                return self._confirmation_row(connection, context, replay[0])
            self._owned_project(connection, context, project_id)
            artifact = self._artifact_row(connection, context, artifact_id)
            if artifact.project_id != project_id:
                raise ContentError("CONTENT_NOT_FOUND", 404)
            expected_kind = {
                DecisionType.READING: ArtifactKind.READING_BRIEF,
                DecisionType.TOPIC: ArtifactKind.TOPIC_PLAN,
                DecisionType.MANUSCRIPT: ArtifactKind.MANUSCRIPT,
            }[decision]
            if artifact.kind is not expected_kind:
                raise ContentError("ARTIFACT_KIND_MISMATCH")
            if decision is DecisionType.READING:
                selected = selection["selectedPointIds"]
                assert isinstance(artifact.body, ReadingBrief)
                available = {point.id for point in artifact.body.points}
                if (
                    not isinstance(selected, list)
                    or not set(cast(list[str], selected)) <= available
                ):
                    raise ContentError("UNKNOWN_SELECTED_POINT")
            elif decision is DecisionType.TOPIC:
                assert isinstance(artifact.body, TopicPlan)
                if selection["topicId"] not in {item.id for item in artifact.body.topics}:
                    raise ContentError("UNKNOWN_TOPIC")
            confirmation_id = uuid4()
            row = connection.execute(
                "INSERT INTO a2flow_content.content_confirmation"
                "(id,project_id,user_id,artifact_id,decision_type,selection_json) "
                f"VALUES(%s,%s,%s,%s,%s,%s::jsonb) RETURNING {CONFIRMATION_COLUMNS}",
                (
                    confirmation_id,
                    project_id,
                    context.user_id,
                    artifact_id,
                    decision.value,
                    canonical_json(selection).decode(),
                ),
            ).fetchone()
            if decision is DecisionType.MANUSCRIPT:
                connection.execute(
                    "UPDATE a2flow_content.content_project SET current_manuscript_id=%s,"
                    "revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=%s AND user_id=%s",
                    (artifact_id, project_id, context.user_id),
                )
            else:
                connection.execute(
                    "UPDATE a2flow_content.content_project SET current_selection_id=%s,"
                    "revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=%s AND user_id=%s",
                    (confirmation_id, project_id, context.user_id),
                )
            self._receipt(connection, context, operation, digest, confirmation_id)
            return _confirmation(row)

    def confirm_reading(
        self, context: TrustedContext, command: ConfirmReadingCommand
    ) -> ConfirmationRecord:
        self._context(context)
        return self._confirm(
            context,
            operation="content.reading.confirm",
            project_id=command.project_id,
            artifact_id=command.artifact_id,
            decision=DecisionType.READING,
            selection={
                "selectedPointIds": list(command.selected_point_ids),
                "userNotes": command.user_notes,
            },
        )

    def confirm_topic(
        self, context: TrustedContext, command: ConfirmTopicCommand
    ) -> ConfirmationRecord:
        self._context(context)
        return self._confirm(
            context,
            operation="content.topic.confirm",
            project_id=command.project_id,
            artifact_id=command.artifact_id,
            decision=DecisionType.TOPIC,
            selection={
                "topicId": command.topic_id,
                "editedTitle": command.edited_title,
                "editedAngle": command.edited_angle,
            },
        )

    def confirm_manuscript(
        self, context: TrustedContext, command: ConfirmManuscriptCommand
    ) -> ConfirmationRecord:
        self._context(context)
        artifact = self.get_artifact(context, command.artifact_id)
        return self._confirm(
            context,
            operation="content.manuscript.confirm",
            project_id=command.project_id,
            artifact_id=command.artifact_id,
            decision=DecisionType.MANUSCRIPT,
            selection={"artifactRevision": artifact.revision},
        )

    def export_manuscript(self, context: TrustedContext, artifact_id: UUID) -> ArtifactRecord:
        artifact = self.get_artifact(context, artifact_id)
        if artifact.kind is not ArtifactKind.MANUSCRIPT:
            raise ContentError("ARTIFACT_KIND_MISMATCH")
        return artifact
