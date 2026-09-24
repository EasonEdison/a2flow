"""Offline release-reader tests; the database double is not PostgreSQL evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

import pytest

from a2flow_capability.models import MAX_I64, Environment, JsonObject, TrustedContext
from a2flow_capability.releases import (
    PostgresReleaseReader,
    ReleasedCapability,
    ReleaseError,
    ReleaseStorageError,
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Rows:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def fetchone(self) -> tuple[object, ...] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class DatabaseDouble:
    def __init__(self) -> None:
        self.database = "management_test"
        self.roots: dict[tuple[str, str], tuple[int, str]] = {}
        self.records: dict[str, str] = {}
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.connects = 0
        self.closed = False
        self.fail = False
        self.transactions = 0

    def connect(
        self,
        conninfo: str,
        *,
        autocommit: bool,
        connect_timeout: int,
        options: str,
        application_name: str,
    ) -> DatabaseDouble:
        del conninfo, autocommit, connect_timeout, options, application_name
        self.connects += 1
        return self

    def close(self) -> None:
        self.closed = True

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.transactions += 1
        yield

    def execute(
        self, query: str, parameters: tuple[object, ...] = ()
    ) -> Rows:
        self.calls.append((query, parameters))
        if self.fail:
            raise RuntimeError("secret database detail")
        if query == "SELECT current_database()":
            return Rows([(self.database,)])
        if query.startswith("SET TRANSACTION") or "WHERE FALSE" in query:
            return Rows([])
        if query.startswith("SELECT revision,state_json"):
            key = (str(parameters[0]), str(parameters[1]))
            row = self.roots.get(key)
            return Rows([] if row is None else [row])
        if query.startswith("SELECT state_json"):
            record_row = self.records.get(str(parameters[1]))
            return Rows([] if record_row is None else [(record_row,)])
        raise AssertionError(f"unexpected SQL: {query}")


def _payload(asset_key: str, action_code: str, revision: int) -> JsonObject:
    return cast(
        JsonObject,
        {
            "draftId": asset_key,
            "revision": revision,
            "status": "EDITING",
            "draft": {
                "basicInfo": {"actionCode": action_code},
                "governance": {"enabled": True, "emergencyDisabled": False},
            },
        },
    )


def _snapshot(asset_key: str, digest: str, revision: int) -> dict[str, object]:
    return {
        "assetType": "CAPABILITY_ACTION",
        "assetKey": asset_key,
        "digest": digest,
        "payloadJson": _json(_payload(asset_key, "probe.invoke", revision)),
    }


def _build(asset_key: str, number: int) -> dict[str, object]:
    digest = f"digest-{number}"
    return {
        "buildId": f"build-{number}",
        "status": "SUCCEEDED",
        "targetVersion": number,
        "sourceDigest": digest,
        "snapshot": _snapshot(asset_key, digest, number),
    }


def _version(asset_key: str, number: int, *, compact: bool = False) -> dict[str, object]:
    digest = f"digest-{number}"
    value: dict[str, object] = {
        "versionId": f"version-{number}",
        "version": number,
        "sourceBuildId": f"build-{number}",
        "inputDigest": digest,
        "sourceDigest": digest,
    }
    if compact:
        value["snapshotBuildId"] = f"build-{number}"
    else:
        value["snapshot"] = _snapshot(asset_key, digest, number)
    return value


def _pointer(environment: str, source_type: str, number: int) -> dict[str, object]:
    source = "build" if source_type == "BUILD" else "version"
    return {
        "environment": environment,
        "sourceType": source_type,
        "sourceId": f"{source}-{number}",
        "version": number,
        "digest": f"digest-{number}",
    }


def _state(
    asset_key: str,
    *,
    environments: dict[str, object],
    builds: list[dict[str, object]] | None = None,
    versions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "assetType": "CAPABILITY_ACTION",
        "assetKey": asset_key,
        "revision": 1,
        "builds": builds or [],
        "versions": versions or [],
        "deployments": [],
        "environments": environments,
        "validations": {},
    }


def _context(environment: Environment, user_id: int = 17) -> TrustedContext:
    return TrustedContext(
        user_id=user_id,
        environment=environment,
        request_id="release-test",
        client="PC",
    )


def _reader(database: DatabaseDouble, environment: Environment) -> PostgresReleaseReader:
    return PostgresReleaseReader(
        "secret-dsn",
        "management_test",
        environment,
        connection_factory=database.connect,
    )


def _install_root(database: DatabaseDouble, asset_key: str, state: dict[str, object]) -> None:
    database.roots[("CAPABILITY_ACTION", asset_key)] = (1, _json(state))


def _record(
    database: DatabaseDouble,
    asset_key: str,
    collection: str,
    identity_field: str,
    payload: dict[str, object],
) -> dict[str, object]:
    envelope = {
        "assetType": "CAPABILITY_ACTION",
        "assetKey": asset_key,
        "collection": collection,
        "recordId": payload[identity_field],
        "payload": payload,
    }
    record_json = _json(envelope)
    reference = hashlib.sha256(record_json.encode()).hexdigest()
    database.records[reference] = _json({"recordJson": record_json})
    return {"recordRef": reference}


def test_prt_resolves_authoritative_build_by_stable_draft_id() -> None:
    database = DatabaseDouble()
    asset_key = "probe-draft"
    state = _state(
        asset_key,
        environments={"PRT": _pointer("PRT", "BUILD", 1)},
        builds=[_build(asset_key, 1)],
    )
    _install_root(database, asset_key, state)

    released = _reader(database, Environment.PRT).resolve(
        asset_key, _context(Environment.PRT)
    )

    assert released == ReleasedCapability(
        asset_key=asset_key,
        source_id="build-1",
        source_digest="digest-1",
        version=1,
        environment=Environment.PRT,
        payload=_payload(asset_key, "probe.invoke", 1),
    )
    root_query = next(call for call in database.calls if call[0].startswith("SELECT revision"))
    assert asset_key not in root_query[0]
    assert root_query[1] == ("CAPABILITY_ACTION", asset_key, 0)
    assert database.transactions == 1


def test_prt_never_falls_back_to_online() -> None:
    database = DatabaseDouble()
    asset_key = "probe-draft"
    _install_root(
        database,
        asset_key,
        _state(
            asset_key,
            environments={"ONLINE": _pointer("ONLINE", "VERSION", 1)},
            versions=[_version(asset_key, 1)],
        ),
    )
    with pytest.raises(ReleaseError, match=r"^PREPROD_POINTER_INVALID$"):
        _reader(database, Environment.PRT).resolve(asset_key, _context(Environment.PRT))


def test_online_uses_java_percentage_and_full_signed64_whitelist() -> None:
    asset_key = "probe-draft"
    database = DatabaseDouble()
    online = _pointer("ONLINE", "VERSION", 1)
    online.update(
        {
            "candidate": {
                "sourceType": "VERSION",
                "sourceId": "version-2",
                "version": 2,
                "digest": "digest-2",
            },
            "grayRule": {
                "percentage": 1,
                "userIdWhitelist": [str(MAX_I64)],
            },
            "grayStatus": "GRAYING",
        }
    )
    _install_root(
        database,
        asset_key,
        _state(
            asset_key,
            environments={"ONLINE": online},
            versions=[_version(asset_key, 1), _version(asset_key, 2)],
        ),
    )
    reader = _reader(database, Environment.ONLINE)

    assert reader.resolve(asset_key, _context(Environment.ONLINE, MAX_I64)).version == 2
    assert reader.resolve(asset_key, _context(Environment.ONLINE, 0)).version == 2
    assert reader.resolve(asset_key, _context(Environment.ONLINE, -1)).version == 1


def test_split_records_and_compact_version_snapshot_are_verified() -> None:
    asset_key = "probe-draft"
    database = DatabaseDouble()
    build = _build(asset_key, 2)
    version = _version(asset_key, 2, compact=True)
    state = _state(
        asset_key,
        environments={"ONLINE": _pointer("ONLINE", "VERSION", 2)},
        builds=[_record(database, asset_key, "builds", "buildId", build)],
        versions=[_record(database, asset_key, "versions", "versionId", version)],
    )
    state["recordStorageVersion"] = 1
    _install_root(database, asset_key, state)

    released = _reader(database, Environment.ONLINE).resolve(
        asset_key, _context(Environment.ONLINE)
    )

    assert released.source_id == "version-2"
    assert released.source_digest == "digest-2"
    assert released.payload["draftId"] == asset_key
    assert database.transactions == 1


def test_compact_version_matches_java_blank_and_invalid_input_digest_rules() -> None:
    asset_key = "probe-draft"
    database = DatabaseDouble()
    build = _build(asset_key, 2)
    build["inputDigest"] = " \t"
    version = _version(asset_key, 2, compact=True)
    state = _state(
        asset_key,
        environments={"ONLINE": _pointer("ONLINE", "VERSION", 2)},
        builds=[_record(database, asset_key, "builds", "buildId", build)],
        versions=[_record(database, asset_key, "versions", "versionId", version)],
    )
    state["recordStorageVersion"] = 1
    _install_root(database, asset_key, state)

    assert (
        _reader(database, Environment.ONLINE)
        .resolve(asset_key, _context(Environment.ONLINE))
        .source_id
        == "version-2"
    )

    database = DatabaseDouble()
    build = _build(asset_key, 2)
    build["inputDigest"] = 7
    version = _version(asset_key, 2, compact=True)
    state = _state(
        asset_key,
        environments={"ONLINE": _pointer("ONLINE", "VERSION", 2)},
        builds=[_record(database, asset_key, "builds", "buildId", build)],
        versions=[_record(database, asset_key, "versions", "versionId", version)],
    )
    state["recordStorageVersion"] = 1
    _install_root(database, asset_key, state)

    with pytest.raises(ReleaseError, match=r"^RELEASE_STATE_INVALID$"):
        _reader(database, Environment.ONLINE).resolve(
            asset_key, _context(Environment.ONLINE)
        )


def test_stable_online_rejects_non_string_gray_status_but_accepts_blank() -> None:
    asset_key = "probe-draft"
    database = DatabaseDouble()
    online = _pointer("ONLINE", "VERSION", 1)
    online["grayStatus"] = " \t"
    _install_root(
        database,
        asset_key,
        _state(
            asset_key,
            environments={"ONLINE": online},
            versions=[_version(asset_key, 1)],
        ),
    )
    reader = _reader(database, Environment.ONLINE)

    assert reader.resolve(asset_key, _context(Environment.ONLINE)).version == 1

    online["grayStatus"] = 7
    _install_root(
        database,
        asset_key,
        _state(
            asset_key,
            environments={"ONLINE": online},
            versions=[_version(asset_key, 1)],
        ),
    )
    with pytest.raises(ReleaseError, match=r"^ONLINE_POINTER_INVALID$"):
        reader.resolve(asset_key, _context(Environment.ONLINE))


def test_tampered_record_and_pointer_identity_fail_closed() -> None:
    asset_key = "probe-draft"
    database = DatabaseDouble()
    build = _build(asset_key, 1)
    reference = _record(database, asset_key, "builds", "buildId", build)
    state = _state(
        asset_key,
        environments={"PRT": _pointer("PRT", "BUILD", 1)},
        builds=[reference],
    )
    state["recordStorageVersion"] = 1
    _install_root(database, asset_key, state)
    record_key = str(reference["recordRef"])
    wrapper = json.loads(database.records[record_key])
    assert isinstance(wrapper, dict)
    wrapper["recordJson"] = str(wrapper["recordJson"]) + " "
    database.records[record_key] = _json(wrapper)

    with pytest.raises(ReleaseError, match=r"^RELEASE_STATE_INVALID$"):
        _reader(database, Environment.PRT).resolve(asset_key, _context(Environment.PRT))

    database = DatabaseDouble()
    bad_build = _build(asset_key, 1)
    bad_build["sourceDigest"] = "another"
    _install_root(
        database,
        asset_key,
        _state(
            asset_key,
            environments={"PRT": _pointer("PRT", "BUILD", 1)},
            builds=[bad_build],
        ),
    )
    with pytest.raises(ReleaseError, match=r"^PREPROD_POINTER_INVALID$"):
        _reader(database, Environment.PRT).resolve(asset_key, _context(Environment.PRT))


def test_context_database_and_storage_errors_remain_distinct() -> None:
    database = DatabaseDouble()
    reader = _reader(database, Environment.PRT)
    with pytest.raises(ReleaseError, match=r"^ENVIRONMENT_MISMATCH$"):
        reader.resolve("probe-draft", _context(Environment.ONLINE))
    assert database.connects == 0

    database.database = "wrong_database"
    with pytest.raises(ReleaseError, match=r"^DATABASE_MISMATCH$"):
        reader.resolve("probe-draft", _context(Environment.PRT))

    database = DatabaseDouble()
    database.fail = True
    with pytest.raises(ReleaseStorageError, match=r"^RELEASE_DATABASE_ERROR$") as failure:
        _reader(database, Environment.PRT).resolve(
            "probe-draft", _context(Environment.PRT)
        )
    assert "secret" not in str(failure.value)


def test_missing_release_disabled_payload_and_invalid_gray_rule_fail_closed() -> None:
    database = DatabaseDouble()
    with pytest.raises(ReleaseError, match=r"^ASSET_NOT_FOUND$"):
        _reader(database, Environment.PRT).resolve(
            "missing-draft", _context(Environment.PRT)
        )

    asset_key = "disabled-draft"
    build = _build(asset_key, 1)
    payload = _payload(asset_key, "disabled.invoke", 1)
    draft = payload["draft"]
    assert isinstance(draft, dict)
    governance = draft["governance"]
    assert isinstance(governance, dict)
    governance["emergencyDisabled"] = True
    snapshot = build["snapshot"]
    assert isinstance(snapshot, dict)
    snapshot["payloadJson"] = _json(payload)
    _install_root(
        database,
        asset_key,
        _state(
            asset_key,
            environments={"PRT": _pointer("PRT", "BUILD", 1)},
            builds=[build],
        ),
    )
    with pytest.raises(ReleaseError, match=r"^ASSET_DISABLED$"):
        _reader(database, Environment.PRT).resolve(asset_key, _context(Environment.PRT))

    database = DatabaseDouble()
    online = _pointer("ONLINE", "VERSION", 1)
    online.update(
        {
            "candidate": _pointer("ONLINE", "VERSION", 2),
            "grayStatus": "GRAYING",
            "grayRule": {"percentage": 5, "userIdWhitelist": ["01"]},
        }
    )
    _install_root(
        database,
        asset_key,
        _state(
            asset_key,
            environments={"ONLINE": online},
            versions=[_version(asset_key, 1), _version(asset_key, 2)],
        ),
    )
    with pytest.raises(ReleaseError, match=r"^ONLINE_POINTER_INVALID$"):
        _reader(database, Environment.ONLINE).resolve(
            asset_key, _context(Environment.ONLINE)
        )


def test_check_ready_is_read_only_and_requires_authority_table() -> None:
    database = DatabaseDouble()
    assert _reader(database, Environment.ONLINE).check_ready()
    statements = [query for query, _ in database.calls]
    assert any("WHERE FALSE" in query for query in statements)
    assert not any(
        query.startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP"))
        for query in statements
    )
