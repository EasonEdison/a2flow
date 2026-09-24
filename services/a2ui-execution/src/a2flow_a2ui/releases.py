"""Read the authoritative published A2UI application snapshot from PostgreSQL."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager, suppress
from typing import Protocol, cast

from a2flow_capability.models import (
    MAX_I64,
    MIN_I64,
    Environment,
    JsonObject,
    JsonValue,
    TrustedContext,
)
from pydantic import ValidationError

from .models import A2uiError, ApplicationBuild, ApplicationRelease, PublishedApplication

_ASSET_TYPE = "A2UI_APPLICATION"
_RECORD_TYPE = "RELEASE_RECORD"
_MAX_STATE_BYTES = 32 * 1024 * 1024


class _Rows(Protocol):
    def fetchone(self) -> tuple[object, ...] | None: ...
    def fetchall(self) -> list[tuple[object, ...]]: ...


class _Connection(Protocol):
    def execute(self, query: str, parameters: tuple[object, ...] = ()) -> _Rows: ...
    def transaction(self) -> AbstractContextManager[object]: ...
    def close(self) -> None: ...


class _Factory(Protocol):
    def __call__(
        self,
        conninfo: str,
        *,
        autocommit: bool,
        connect_timeout: int,
        options: str,
        application_name: str,
    ) -> _Connection: ...


def _connect(
    conninfo: str, *, autocommit: bool, connect_timeout: int, options: str, application_name: str
) -> _Connection:
    import psycopg

    return cast(
        _Connection,
        psycopg.connect(
            conninfo,
            autocommit=autocommit,
            connect_timeout=connect_timeout,
            options=options,
            application_name=application_name,
        ),
    )


class PostgresApplicationReader:
    """Resolve exactly one environment without cross-environment fallback."""

    def __init__(
        self,
        conninfo: str,
        database: str,
        environment: Environment | str,
        *,
        connection_factory: _Factory | None = None,
    ) -> None:
        if not conninfo or not database:
            raise ValueError("database configuration required")
        try:
            self.environment = Environment(environment)
        except (TypeError, ValueError):
            raise ValueError("environment must be PRT or ONLINE") from None
        self._conninfo = conninfo
        self._database = database
        self._connect = connection_factory or _connect

    def check_ready(self) -> bool:
        with self._connection() as connection, connection.transaction():
            self._prepare(connection)
            connection.execute(
                "SELECT asset_type,asset_key,revision,state_json,deleted "
                "FROM skill_asset_release_state WHERE FALSE"
            ).fetchall()
        return True

    def current(self, app_code: str, context: TrustedContext) -> PublishedApplication:
        if type(app_code) is not str or not app_code.strip() or len(app_code) > 256:
            raise A2uiError("A2UI_REQUEST_INVALID")
        if type(context) is not TrustedContext:
            raise A2uiError("TRUSTED_CONTEXT_REQUIRED")
        if context.environment is not self.environment:
            raise A2uiError("A2UI_ENVIRONMENT_MISMATCH")
        with self._connection() as connection, connection.transaction():
            self._prepare(connection)
            row = connection.execute(
                "SELECT state_json FROM skill_asset_release_state "
                "WHERE asset_type=%s AND asset_key=%s AND deleted=%s",
                (_ASSET_TYPE, app_code, 0),
            ).fetchone()
            if row is None or len(row) != 1 or type(row[0]) is not str:
                raise A2uiError("A2UI_APPLICATION_RELEASE_NOT_AVAILABLE")
            state = self._hydrate(connection, app_code, row[0])
            return self._resolve(app_code, context.user_id, state)

    @contextmanager
    def _connection(self) -> Iterator[_Connection]:
        connection: _Connection | None = None
        try:
            connection = self._connect(
                self._conninfo,
                autocommit=True,
                connect_timeout=5,
                options="-c statement_timeout=10000 -c lock_timeout=5000",
                application_name="a2flow-a2ui-release-reader",
            )
            yield connection
        except A2uiError:
            raise
        except Exception:
            raise A2uiError("A2UI_RELEASE_DATABASE_ERROR") from None
        finally:
            if connection is not None:
                with suppress(Exception):
                    connection.close()

    def _prepare(self, connection: _Connection) -> None:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        if connection.execute("SELECT current_database()").fetchone() != (self._database,):
            raise A2uiError("A2UI_DATABASE_MISMATCH")

    def _hydrate(self, connection: _Connection, app_code: str, source: str) -> JsonObject:
        root = _json_object(source, "A2UI_RELEASE_STATE_INVALID")
        if root.get("assetType") != _ASSET_TYPE or root.get("assetKey") != app_code:
            raise A2uiError("A2UI_RELEASE_STATE_INVALID")
        storage = root.get("recordStorageVersion")
        if storage is None:
            return root
        if type(storage) is not int or storage != 1:
            raise A2uiError("A2UI_RELEASE_STATE_INVALID")
        hydrated = dict(root)
        del hydrated["recordStorageVersion"]
        identities = {"builds": "buildId", "versions": "versionId", "deployments": "deploymentId"}
        for collection, identity_field in identities.items():
            records = [
                self._entry(connection, app_code, collection, identity_field, value)
                for value in _object_list(hydrated.get(collection))
            ]
            _index(records, identity_field)
            hydrated[collection] = cast(JsonValue, records)
        builds = _object_list(hydrated.get("builds"))
        build_index = _index(builds, "buildId")
        for version in _object_list(hydrated.get("versions")):
            if "snapshotBuildId" not in version:
                continue
            if "snapshot" in version:
                raise A2uiError("A2UI_RELEASE_STATE_INVALID")
            build_id = _text(version.pop("snapshotBuildId"))
            build = build_index.get(build_id)
            if (
                build is None
                or version.get("sourceBuildId") != build_id
                or version.get("sourceDigest") != build.get("sourceDigest")
            ):
                raise A2uiError("A2UI_RELEASE_STATE_INVALID")
            build_input = build.get("inputDigest") or build.get("sourceDigest")
            if version.get("inputDigest") != build_input or type(build.get("snapshot")) is not dict:
                raise A2uiError("A2UI_RELEASE_STATE_INVALID")
            version["snapshot"] = build["snapshot"]
        return hydrated

    def _entry(
        self,
        connection: _Connection,
        app_code: str,
        collection: str,
        identity_field: str,
        entry: JsonObject,
    ) -> JsonObject:
        if "recordRef" not in entry:
            return entry
        if set(entry) != {"recordRef"}:
            raise A2uiError("A2UI_RELEASE_STATE_INVALID")
        reference = _text(entry["recordRef"])
        row = connection.execute(
            "SELECT state_json FROM skill_asset_release_state "
            "WHERE asset_type=%s AND asset_key=%s AND deleted=%s",
            (_RECORD_TYPE, reference, 0),
        ).fetchone()
        if row is None or len(row) != 1 or type(row[0]) is not str:
            raise A2uiError("A2UI_RELEASE_STATE_INVALID")
        wrapper = _json_object(row[0], "A2UI_RELEASE_STATE_INVALID")
        if set(wrapper) != {"recordJson"}:
            raise A2uiError("A2UI_RELEASE_STATE_INVALID")
        record_json = _text(wrapper["recordJson"])
        if hashlib.sha256(record_json.encode()).hexdigest() != reference:
            raise A2uiError("A2UI_RELEASE_STATE_INVALID")
        envelope = _json_object(record_json, "A2UI_RELEASE_STATE_INVALID")
        payload = _object(envelope.get("payload"))
        record_id = _text(envelope.get("recordId"))
        if (
            envelope.get("assetType") != _ASSET_TYPE
            or envelope.get("assetKey") != app_code
            or envelope.get("collection") != collection
            or payload.get(identity_field) != record_id
        ):
            raise A2uiError("A2UI_RELEASE_STATE_INVALID")
        return payload

    def _resolve(self, app_code: str, user_id: int, state: JsonObject) -> PublishedApplication:
        environments = _object(state.get("environments"))
        raw_pointer = environments.get(self.environment.value)
        if raw_pointer is None:
            raise A2uiError("A2UI_APPLICATION_RELEASE_NOT_AVAILABLE")
        pointer = _object(raw_pointer)
        if self.environment is Environment.ONLINE:
            pointer = self._online(pointer, user_id)
        source_type = "BUILD" if self.environment is Environment.PRT else "VERSION"
        code = "A2UI_APPLICATION_RELEASE_NOT_AVAILABLE"
        if (
            pointer.get("environment") != self.environment.value
            or pointer.get("sourceType") != source_type
        ):
            raise A2uiError(code)
        source_id, digest = _text(pointer.get("sourceId")), _text(pointer.get("digest"))
        version = _integer(pointer.get("version"))
        collection, identity = (
            ("builds", "buildId")
            if self.environment is Environment.PRT
            else ("versions", "versionId")
        )
        matches = [
            item for item in _object_list(state.get(collection)) if item.get(identity) == source_id
        ]
        if len(matches) != 1:
            raise A2uiError(code)
        release = matches[0]
        version_field = "targetVersion" if self.environment is Environment.PRT else "version"
        if (
            (self.environment is Environment.PRT and release.get("status") != "SUCCEEDED")
            or release.get(version_field) != version
            or release.get("sourceDigest") != digest
        ):
            raise A2uiError(code)
        snapshot = _object(release.get("snapshot"))
        if (
            snapshot.get("assetType") != _ASSET_TYPE
            or snapshot.get("assetKey") != app_code
            or snapshot.get("digest") != digest
        ):
            raise A2uiError(code)
        payload_json = _text(snapshot.get("payloadJson"))
        if (
            len(payload_json.encode()) > 1024 * 1024
            or digest != "sha256:" + hashlib.sha256(payload_json.encode()).hexdigest()
        ):
            raise A2uiError("A2UI_PUBLISHED_DIGEST_MISMATCH")
        try:
            build = ApplicationBuild.model_validate_json(payload_json)
        except ValidationError:
            raise A2uiError("A2UI_PUBLISHED_BUILD_INVALID") from None
        if (
            build.app_code != app_code
            or build.publication_environment is not self.environment
            or not build.app_build_id.strip()
        ):
            raise A2uiError("A2UI_PUBLISHED_BUILD_INVALID")
        identity_value = ApplicationRelease(
            app_code, source_id, digest, build.app_build_id, self.environment
        )
        return PublishedApplication(identity_value, build)

    def _online(self, state: JsonObject, user_id: int) -> JsonObject:
        candidate = state.get("candidate")
        if candidate is None:
            if state.get("grayRule") is not None or state.get("grayStatus") not in {None, "STABLE"}:
                raise A2uiError("A2UI_APPLICATION_RELEASE_NOT_AVAILABLE")
            return state
        if state.get("grayStatus") != "GRAYING":
            raise A2uiError("A2UI_APPLICATION_RELEASE_NOT_AVAILABLE")
        candidate_obj, rule = _object(candidate), _object(state.get("grayRule"))
        percentage = _integer(rule.get("percentage"))
        whitelist_raw = rule.get("userIdWhitelist")
        if not 0 <= percentage <= 100 or type(whitelist_raw) is not list:
            raise A2uiError("A2UI_APPLICATION_RELEASE_NOT_AVAILABLE")
        whitelist = [_user_id(item) for item in whitelist_raw]
        if len(whitelist) != len(set(whitelist)):
            raise A2uiError("A2UI_APPLICATION_RELEASE_NOT_AVAILABLE")
        if not (percentage == 100 or user_id in whitelist or user_id % 100 < percentage):
            return state
        return {
            "environment": state.get("environment"),
            "sourceType": candidate_obj.get("sourceType"),
            "sourceId": candidate_obj.get("sourceId"),
            "version": candidate_obj.get("version"),
            "digest": candidate_obj.get("digest"),
        }


def _json_object(source: str, code: str) -> JsonObject:
    try:
        if len(source.encode()) > _MAX_STATE_BYTES:
            raise A2uiError(code)
        return _object(cast(JsonValue, json.loads(source)))
    except A2uiError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise A2uiError(code) from None


def _object(value: object) -> JsonObject:
    if type(value) is not dict:
        raise A2uiError("A2UI_RELEASE_STATE_INVALID")
    return cast(JsonObject, value)


def _object_list(value: object) -> list[JsonObject]:
    if value is None:
        return []
    if type(value) is not list:
        raise A2uiError("A2UI_RELEASE_STATE_INVALID")
    return [_object(item) for item in value]


def _index(values: Sequence[JsonObject], field: str) -> dict[str, JsonObject]:
    result: dict[str, JsonObject] = {}
    for value in values:
        key = _text(value.get(field))
        if key in result:
            raise A2uiError("A2UI_RELEASE_STATE_INVALID")
        result[key] = value
    return result


def _text(value: object) -> str:
    if type(value) is not str or not value:
        raise A2uiError("A2UI_RELEASE_STATE_INVALID")
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        raise A2uiError("A2UI_RELEASE_STATE_INVALID")
    return value


def _user_id(value: object) -> int:
    if type(value) is int:
        parsed = value
    elif type(value) is str and value and len(value) <= 20:
        try:
            parsed = int(value)
        except ValueError:
            raise A2uiError("A2UI_RELEASE_STATE_INVALID") from None
        if str(parsed) != value:
            raise A2uiError("A2UI_RELEASE_STATE_INVALID")
    else:
        raise A2uiError("A2UI_RELEASE_STATE_INVALID")
    if not MIN_I64 <= parsed <= MAX_I64:
        raise A2uiError("A2UI_RELEASE_STATE_INVALID")
    return parsed
