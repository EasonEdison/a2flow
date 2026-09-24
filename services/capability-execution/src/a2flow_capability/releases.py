"""Read the authoritative published capability snapshot from management PostgreSQL.

The management aggregate is the release authority.  Runtime asset-store rows are
only a projection and are deliberately not consulted here.  One reader instance
is bound to one requested environment and one exact management database.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import dataclass
from typing import Protocol, cast

from .models import MAX_I64, MIN_I64, Environment, JsonObject, JsonValue, TrustedContext

_ASSET_TYPE = "CAPABILITY_ACTION"
_RECORD_TYPE = "RELEASE_RECORD"
_NOT_DELETED = 0
_RECORD_STORAGE_VERSION = 1
_COLLECTION_IDS = {
    "builds": "buildId",
    "versions": "versionId",
    "deployments": "deploymentId",
}
_MAX_STATE_BYTES = 32 * 1024 * 1024


class ReleaseError(RuntimeError):
    """Stable non-sensitive failure for unavailable or corrupt release state."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReleaseStorageError(RuntimeError):
    """Database connectivity/driver failure, distinct from a missing release."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ReleasedCapability:
    asset_key: str
    source_id: str
    source_digest: str
    version: int
    environment: Environment
    payload: JsonObject


class _Rows(Protocol):
    def fetchone(self) -> tuple[object, ...] | None: ...

    def fetchall(self) -> list[tuple[object, ...]]: ...


class _Connection(Protocol):
    def execute(
        self, query: str, parameters: tuple[object, ...] = ()
    ) -> _Rows: ...

    def transaction(self) -> AbstractContextManager[object]: ...

    def close(self) -> None: ...


class _ConnectionFactory(Protocol):
    def __call__(
        self,
        conninfo: str,
        *,
        autocommit: bool,
        connect_timeout: int,
        options: str,
        application_name: str,
    ) -> _Connection: ...


def _default_connect(
    conninfo: str,
    *,
    autocommit: bool,
    connect_timeout: int,
    options: str,
    application_name: str,
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


class PostgresReleaseReader:
    """Read one environment's current capability release without fallback or DDL."""

    def __init__(
        self,
        conninfo: str,
        database: str,
        environment: Environment | str,
        *,
        connection_factory: _ConnectionFactory | None = None,
    ) -> None:
        if type(conninfo) is not str or not conninfo:
            raise ValueError("conninfo is required")
        if type(database) is not str or not database:
            raise ValueError("database is required")
        try:
            bound_environment = Environment(environment)
        except (TypeError, ValueError):
            raise ValueError("environment must be PRT or ONLINE") from None
        self._conninfo = conninfo
        self._database = database
        self.environment = bound_environment
        self._connect = connection_factory or _default_connect

    def check_ready(self) -> bool:
        """Verify the exact database and authority schema using a read-only transaction."""
        with self._connection() as connection, connection.transaction():
            self._set_read_only(connection)
            self._check_database(connection)
            connection.execute(
                "SELECT asset_type,asset_key,revision,state_json,deleted "
                "FROM skill_asset_release_state WHERE FALSE"
            ).fetchall()
        return True

    def resolve(self, asset_key: str, context: TrustedContext) -> ReleasedCapability:
        if type(asset_key) is not str or not asset_key.strip() or len(asset_key) > 256:
            raise ReleaseError("ASSET_REFERENCE_INVALID")
        if type(context) is not TrustedContext:
            raise ReleaseError("TRUSTED_CONTEXT_REQUIRED")
        if context.environment is not self.environment:
            raise ReleaseError("ENVIRONMENT_MISMATCH")

        with self._connection() as connection, connection.transaction():
            self._set_read_only(connection)
            self._check_database(connection)
            row = connection.execute(
                "SELECT revision,state_json FROM skill_asset_release_state "
                "WHERE asset_type=%s AND asset_key=%s AND deleted=%s",
                (_ASSET_TYPE, asset_key, _NOT_DELETED),
            ).fetchone()
            if row is None:
                raise ReleaseError("ASSET_NOT_FOUND")
            if len(row) != 2 or type(row[0]) is not int or type(row[1]) is not str:
                raise ReleaseError("RELEASE_STATE_INVALID")
            state = self._hydrate(connection, asset_key, row[1])
            return self._resolve_state(asset_key, context, state)

    @contextmanager
    def _connection(self) -> Iterator[_Connection]:
        connection: _Connection | None = None
        try:
            connection = self._connect(
                self._conninfo,
                autocommit=True,
                connect_timeout=5,
                options="-c statement_timeout=10000 -c lock_timeout=5000",
                application_name="a2flow-capability-release-reader",
            )
            yield connection
        except (ReleaseError, ReleaseStorageError):
            raise
        except Exception:
            raise ReleaseStorageError("RELEASE_DATABASE_ERROR") from None
        finally:
            if connection is not None:
                with suppress(Exception):
                    connection.close()

    def _set_read_only(self, connection: _Connection) -> None:
        connection.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        )

    def _check_database(self, connection: _Connection) -> None:
        row = connection.execute("SELECT current_database()").fetchone()
        if row != (self._database,):
            raise ReleaseError("DATABASE_MISMATCH")

    def _hydrate(
        self, connection: _Connection, asset_key: str, state_json: str
    ) -> JsonObject:
        root = _json_object(state_json, "RELEASE_STATE_INVALID")
        if root.get("assetType") != _ASSET_TYPE or root.get("assetKey") != asset_key:
            raise ReleaseError("RELEASE_STATE_INVALID")
        storage_version = root.get("recordStorageVersion")
        if storage_version is None:
            return root
        if type(storage_version) is not int or storage_version != _RECORD_STORAGE_VERSION:
            raise ReleaseError("RELEASE_STATE_INVALID")

        hydrated = dict(root)
        del hydrated["recordStorageVersion"]
        for collection, identity_field in _COLLECTION_IDS.items():
            entries = _object_list(hydrated.get(collection), "RELEASE_STATE_INVALID")
            records = [
                self._hydrate_entry(
                    connection, asset_key, collection, identity_field, entry
                )
                for entry in entries
            ]
            _index_unique(records, identity_field)
            hydrated[collection] = [cast(JsonValue, record) for record in records]
        self._restore_version_snapshots(hydrated)
        return hydrated

    def _hydrate_entry(
        self,
        connection: _Connection,
        asset_key: str,
        collection: str,
        identity_field: str,
        entry: JsonObject,
    ) -> JsonObject:
        if "recordRef" not in entry:
            return entry
        if set(entry) != {"recordRef"}:
            raise ReleaseError("RELEASE_STATE_INVALID")
        reference = _required_text(entry.get("recordRef"), "RELEASE_STATE_INVALID")
        row = connection.execute(
            "SELECT state_json FROM skill_asset_release_state "
            "WHERE asset_type=%s AND asset_key=%s AND deleted=%s",
            (_RECORD_TYPE, reference, _NOT_DELETED),
        ).fetchone()
        if row is None or len(row) != 1 or type(row[0]) is not str:
            raise ReleaseError("RELEASE_STATE_INVALID")
        wrapper = _json_object(row[0], "RELEASE_STATE_INVALID")
        if set(wrapper) != {"recordJson"}:
            raise ReleaseError("RELEASE_STATE_INVALID")
        record_json = _required_text(wrapper.get("recordJson"), "RELEASE_STATE_INVALID")
        if hashlib.sha256(record_json.encode("utf-8")).hexdigest() != reference:
            raise ReleaseError("RELEASE_STATE_INVALID")
        envelope = _json_object(record_json, "RELEASE_STATE_INVALID")
        if (
            envelope.get("assetType") != _ASSET_TYPE
            or envelope.get("assetKey") != asset_key
            or envelope.get("collection") != collection
        ):
            raise ReleaseError("RELEASE_STATE_INVALID")
        payload = _object(envelope.get("payload"), "RELEASE_STATE_INVALID")
        record_id = _required_text(envelope.get("recordId"), "RELEASE_STATE_INVALID")
        if payload.get(identity_field) != record_id:
            raise ReleaseError("RELEASE_STATE_INVALID")
        return payload

    def _restore_version_snapshots(self, root: JsonObject) -> None:
        builds = _object_list(root.get("builds"), "RELEASE_STATE_INVALID")
        versions = _object_list(root.get("versions"), "RELEASE_STATE_INVALID")
        build_index = _index_unique(builds, "buildId")
        for version in versions:
            if "snapshotBuildId" not in version:
                continue
            if "snapshot" in version:
                raise ReleaseError("RELEASE_STATE_INVALID")
            build_id = _required_text(
                version.pop("snapshotBuildId"), "RELEASE_STATE_INVALID"
            )
            if version.get("sourceBuildId") != build_id:
                raise ReleaseError("RELEASE_STATE_INVALID")
            build = build_index.get(build_id)
            if build is None or type(build.get("snapshot")) is not dict:
                raise ReleaseError("RELEASE_STATE_INVALID")
            if version.get("sourceDigest") != build.get("sourceDigest"):
                raise ReleaseError("RELEASE_STATE_INVALID")
            build_input = build.get("inputDigest")
            if build_input is not None and type(build_input) is not str:
                raise ReleaseError("RELEASE_STATE_INVALID")
            if build_input is None or not build_input.strip():
                build_input = _required_text(
                    build.get("sourceDigest"), "RELEASE_STATE_INVALID"
                )
            if version.get("inputDigest") != build_input:
                raise ReleaseError("RELEASE_STATE_INVALID")
            version["snapshot"] = build["snapshot"]

    def _resolve_state(
        self, asset_key: str, context: TrustedContext, state: JsonObject
    ) -> ReleasedCapability:
        environments = _object(state.get("environments"), "RELEASE_STATE_INVALID")
        environment_state = environments.get(self.environment.value)
        if environment_state is None:
            code = (
                "PREPROD_POINTER_INVALID"
                if self.environment is Environment.PRT
                else "ONLINE_POINTER_REQUIRED"
            )
            raise ReleaseError(code)
        selected = _object(environment_state, self._pointer_error())
        if self.environment is Environment.ONLINE:
            selected = self._select_online_pointer(selected, context.user_id)

        expected_source_type = "BUILD" if self.environment is Environment.PRT else "VERSION"
        if (
            selected.get("environment") != self.environment.value
            or selected.get("sourceType") != expected_source_type
        ):
            raise ReleaseError(self._pointer_error())
        source_id = _required_text(selected.get("sourceId"), self._pointer_error())
        version = _required_int(selected.get("version"), self._pointer_error())
        digest = _required_text(selected.get("digest"), self._pointer_error())

        collection = "builds" if self.environment is Environment.PRT else "versions"
        identity_field = "buildId" if self.environment is Environment.PRT else "versionId"
        candidates = _object_list(state.get(collection), "RELEASE_STATE_INVALID")
        matches = [item for item in candidates if item.get(identity_field) == source_id]
        if len(matches) != 1:
            raise ReleaseError(self._pointer_error())
        release = matches[0]
        if self.environment is Environment.PRT and release.get("status") != "SUCCEEDED":
            raise ReleaseError(self._pointer_error())
        release_version_field = (
            "targetVersion" if self.environment is Environment.PRT else "version"
        )
        if (
            release.get(release_version_field) != version
            or release.get("sourceDigest") != digest
        ):
            raise ReleaseError(self._pointer_error())
        snapshot = _object(release.get("snapshot"), self._pointer_error())
        if (
            snapshot.get("assetType") != _ASSET_TYPE
            or snapshot.get("assetKey") != asset_key
            or snapshot.get("digest") != digest
        ):
            raise ReleaseError(self._pointer_error())
        payload_json = _required_text(snapshot.get("payloadJson"), self._pointer_error())
        payload = _json_object(payload_json, self._pointer_error())
        self._validate_payload(asset_key, payload)
        return ReleasedCapability(
            asset_key=asset_key,
            source_id=source_id,
            source_digest=digest,
            version=version,
            environment=self.environment,
            payload=payload,
        )

    def _select_online_pointer(self, state: JsonObject, user_id: int) -> JsonObject:
        candidate_value = state.get("candidate")
        rule_value = state.get("grayRule")
        gray_status = state.get("grayStatus")
        if candidate_value is None:
            if gray_status is not None and type(gray_status) is not str:
                raise ReleaseError("ONLINE_POINTER_INVALID")
            if rule_value is not None or (
                type(gray_status) is str
                and gray_status.strip()
                and gray_status != "STABLE"
            ):
                raise ReleaseError("ONLINE_POINTER_INVALID")
            return state
        candidate = _object(candidate_value, "ONLINE_POINTER_INVALID")
        rule = _object(rule_value, "ONLINE_POINTER_INVALID")
        if gray_status != "GRAYING":
            raise ReleaseError("ONLINE_POINTER_INVALID")
        percentage = _required_int(rule.get("percentage"), "ONLINE_POINTER_INVALID")
        if not 0 <= percentage <= 100:
            raise ReleaseError("ONLINE_POINTER_INVALID")
        whitelist_values = rule.get("userIdWhitelist")
        if type(whitelist_values) is not list:
            raise ReleaseError("ONLINE_POINTER_INVALID")
        whitelist = [_wire_user_id(value) for value in whitelist_values]
        if len(whitelist) != len(set(whitelist)):
            raise ReleaseError("ONLINE_POINTER_INVALID")
        use_candidate = (
            percentage == 100
            or user_id in whitelist
            or user_id % 100 < percentage
        )
        if not use_candidate:
            return state
        return {
            "environment": state.get("environment"),
            "sourceType": candidate.get("sourceType"),
            "sourceId": candidate.get("sourceId"),
            "version": candidate.get("version"),
            "digest": candidate.get("digest"),
        }

    def _validate_payload(self, asset_key: str, payload: JsonObject) -> None:
        if payload.get("draftId") != asset_key:
            raise ReleaseError(self._pointer_error())
        draft = _object(payload.get("draft"), self._pointer_error())
        if not draft:
            raise ReleaseError(self._pointer_error())
        basic = _object(draft.get("basicInfo"), self._pointer_error())
        _required_text(basic.get("actionCode"), self._pointer_error())
        governance_value = draft.get("governance")
        governance = (
            governance_value if type(governance_value) is dict else {}
        )
        if (
            governance.get("enabled") is False
            or governance.get("emergencyDisabled") is True
            or (
                type(payload.get("status")) is str
                and cast(str, payload.get("status")).upper() == "DISABLED"
            )
        ):
            raise ReleaseError("ASSET_DISABLED")

    def _pointer_error(self) -> str:
        return (
            "PREPROD_POINTER_INVALID"
            if self.environment is Environment.PRT
            else "ONLINE_POINTER_INVALID"
        )


def _json_object(source: str, code: str) -> JsonObject:
    try:
        if len(source.encode("utf-8")) > _MAX_STATE_BYTES:
            raise ReleaseError(code)
        value = cast(JsonValue, json.loads(source))
    except ReleaseError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ReleaseError(code) from None
    return _object(value, code)


def _object(value: object, code: str) -> JsonObject:
    if type(value) is not dict:
        raise ReleaseError(code)
    return cast(JsonObject, value)


def _object_list(value: object, code: str) -> list[JsonObject]:
    if value is None:
        return []
    if type(value) is not list:
        raise ReleaseError(code)
    return [_object(item, code) for item in value]


def _index_unique(values: Sequence[JsonObject], identity_field: str) -> dict[str, JsonObject]:
    result: dict[str, JsonObject] = {}
    for value in values:
        identity = _required_text(value.get(identity_field), "RELEASE_STATE_INVALID")
        if identity in result:
            raise ReleaseError("RELEASE_STATE_INVALID")
        result[identity] = value
    return result


def _required_text(value: object, code: str) -> str:
    if type(value) is not str or not value:
        raise ReleaseError(code)
    return value


def _required_int(value: object, code: str) -> int:
    if type(value) is not int:
        raise ReleaseError(code)
    return value


def _wire_user_id(value: object) -> int:
    if type(value) is int:
        parsed = value
    elif type(value) is str and value and len(value) <= 20:
        if value == "0":
            parsed = 0
        elif (
            value[0] == "-" and value[1:].isdigit() and value[1] != "0"
        ) or (value.isdigit() and value[0] != "0"):
            parsed = int(value)
        else:
            raise ReleaseError("ONLINE_POINTER_INVALID")
    else:
        raise ReleaseError("ONLINE_POINTER_INVALID")
    if type(parsed) is not int or not MIN_I64 <= parsed <= MAX_I64:
        raise ReleaseError("ONLINE_POINTER_INVALID")
    return parsed
