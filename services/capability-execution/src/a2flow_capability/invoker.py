"""Resolve action codes through the retained index, authorize with M publications.

The inventory only supplies stable draft identity. It never chooses a serving
version: every call resolves the authoritative M pointer again before execution.
"""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

import psycopg

from .compiler import compile_capability
from .executor import CapabilityExecutor
from .models import Environment, ExecutionResult, JsonObject, TrustedContext
from .releases import PostgresReleaseReader, ReleaseError, ReleaseStorageError


class CapabilityIndex(Protocol):
    def asset_key(self, action_code: str, context: TrustedContext) -> str: ...


def indexed_identity(raw: bytes, expected: str, action_code: str) -> str:
    if len(raw) > 16 * 1024 * 1024 or "sha256:" + hashlib.sha256(raw).hexdigest() != expected:
        raise ReleaseError("CAPABILITY_INDEX_DIGEST_INVALID")
    document: object = json.loads(raw)
    if not isinstance(document, dict):
        raise ReleaseError("CAPABILITY_INDEX_INVALID")
    if document.get("kind") != "ABILITY" or document.get("key") != action_code:
        raise ReleaseError("CAPABILITY_INDEX_IDENTITY_INVALID")
    definition = document.get("definition")
    if not isinstance(definition, dict) or definition.get("runtimeProfile") != "a2flow.java-rpc.v1":
        raise ReleaseError("CAPABILITY_INDEX_PROFILE_INVALID")
    key = definition.get("assetKey")
    if type(key) is not str or not key or len(key) > 256:
        raise ReleaseError("CAPABILITY_INDEX_IDENTITY_INVALID")
    return key


class PostgresCapabilityIndex:
    def __init__(
        self, conninfo: str, database: str, environment: Environment, namespace: str
    ) -> None:
        if (
            not conninfo
            or not database
            or not namespace
            or not isinstance(environment, Environment)
        ):
            raise ValueError("explicit capability inventory configuration required")
        self._conninfo = conninfo
        self._database = database
        self._environment = environment
        self._namespace = namespace

    def asset_key(self, action_code: str, context: TrustedContext) -> str:
        if context.environment != self._environment:
            raise ReleaseError("ENVIRONMENT_MISMATCH")
        if not action_code or len(action_code) > 256:
            raise ReleaseError("CAPABILITY_REFERENCE_INVALID")
        try:
            with psycopg.connect(
                self._conninfo,
                autocommit=True,
                connect_timeout=5,
                options="-c statement_timeout=5000",
            ) as connection, connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                if connection.execute("SELECT current_database()").fetchone() != (
                    self._database,
                ):
                    raise ReleaseError("DATABASE_MISMATCH")
                if connection.execute(
                    "SELECT environment FROM a2flow_asset_environment WHERE singleton=TRUE"
                ).fetchone() != (self._environment.value,):
                    raise ReleaseError("ENVIRONMENT_MISMATCH")
                # Stream retained entries to avoid loading all historical payloads at once.
                cursor = connection.execute(
                    "SELECT document,digest FROM a2flow_asset_versions "
                    "WHERE namespace=%s AND kind='ABILITY' AND asset_key=%s",
                    (self._namespace, action_code),
                )
                identities: set[str] = set()
                for raw, digest in cursor:
                    if not isinstance(raw, bytes | memoryview) or type(digest) is not str:
                        raise ReleaseError("CAPABILITY_INDEX_INVALID")
                    identities.add(indexed_identity(bytes(raw), digest, action_code))
                    if len(identities) > 1:
                        raise ReleaseError("CAPABILITY_INDEX_AMBIGUOUS")
            if not identities:
                raise ReleaseError("CAPABILITY_INDEX_NOT_FOUND")
            return next(iter(identities))
        except ReleaseError:
            raise
        except (ValueError, UnicodeError):
            raise ReleaseError("CAPABILITY_INDEX_INVALID") from None
        except psycopg.Error:
            raise ReleaseStorageError("CAPABILITY_INDEX_UNAVAILABLE") from None


class PublishedCapabilityInvoker:
    def __init__(
        self, reader: PostgresReleaseReader, executor: CapabilityExecutor, index: CapabilityIndex
    ) -> None:
        self._reader = reader
        self._executor = executor
        self._index = index

    def execute_action_code(
        self, action_code: str, arguments: JsonObject, context: TrustedContext
    ) -> ExecutionResult:
        key = self._index.asset_key(action_code, context)
        release = self._reader.resolve(key, context)
        compiled = compile_capability(
            release.payload,
            release.source_id,
            release.source_digest,
            release.environment,
            release.version,
            context.client,
        )
        if compiled.plan.action_code != action_code:
            raise ReleaseError("CAPABILITY_ACTION_CODE_MISMATCH")
        return self._executor.execute(compiled.plan, arguments, context)
