"""Small immutable persistence records; these are not shared wire contracts."""

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, cast

from skillweave_contracts.asset_types import (
    ASSET_KINDS,
    AssetIdentity,
    AssetKind,
    EffectiveVersions,
    Environment,
    JsonObject,
    JsonValue,
    ServingState,
)
from skillweave_contracts.user_id import user_id_from_wire

MAX_BYTES = 16 * 1024 * 1024
MAX_ASSETS = 128
KINDS = ASSET_KINDS


class AbilityPublicationMetadata(Protocol):
    adapter_operation_ref: str


class AssetError(ValueError):
    """Non-sensitive failure code; never include connection strings or payload."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def canonical(value: JsonValue) -> bytes:
    try:
        data = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise AssetError("INVALID_JSON") from None
    if len(data) > MAX_BYTES:
        raise AssetError("BUNDLE_TOO_LARGE")
    return data


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def closed(value: object, keys: set[str] | frozenset[str]) -> None:
    if type(value) is not dict or set(value) != set(keys):
        raise AssetError("INVALID_FIELDS")


@dataclass(frozen=True)
class Asset:
    kind: AssetKind
    key: str
    asset_id: str
    version_id: str
    data: bytes
    content_digest: str

    @property
    def document(self) -> JsonObject:
        return cast(JsonObject, json.loads(self.data))

    @property
    def definition(self) -> JsonObject:
        return cast(JsonObject, self.document["definition"])

    @property
    def identity(self) -> tuple[AssetKind, str, str]:
        return self.kind, self.key, self.version_id

    @property
    def asset_identity(self) -> AssetIdentity:
        return AssetIdentity(self.kind, self.key)


@dataclass(frozen=True)
class Bundle:
    namespace: str
    environment: Environment
    assets: tuple[Asset, ...]
    serving_data: bytes

    @property
    def serving(self) -> list[ServingState]:
        raw_states = cast(list[dict[str, JsonValue]], json.loads(self.serving_data))
        return [
            {
                "kind": cast(AssetKind, state["kind"]),
                "key": cast(str, state["key"]),
                "current": cast(str | None, state["current"]),
                "stable": cast(str | None, state["stable"]),
                "gray": cast(str | None, state["gray"]),
                "grayUserIds": [
                    user_id_from_wire(user) for user in cast(list[JsonValue], state["grayUserIds"])
                ],
            }
            for state in raw_states
        ]


@dataclass(frozen=True)
class ResolvedWorkflow:
    data: bytes
    effective_versions: EffectiveVersions

    @property
    def definition(self) -> JsonObject:
        return cast(JsonObject, json.loads(self.data))


@dataclass(frozen=True)
class ResolvedAbility:
    data: bytes
    publication_metadata: AbilityPublicationMetadata
    effective_versions: EffectiveVersions
    asset_id: str
    version_id: str
    content_digest: str

    @property
    def definition(self) -> JsonObject:
        return cast(JsonObject, json.loads(self.data))

    @property
    def operation_ref(self) -> str:
        return self.publication_metadata.adapter_operation_ref
