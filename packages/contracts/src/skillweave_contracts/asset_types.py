"""Shared, dependency-neutral asset identities and JSON value types."""

from dataclasses import dataclass
from typing import Final, Literal, TypeAlias, TypedDict

AssetKind: TypeAlias = Literal["SKILL", "ABILITY", "APPLICATION", "COMPONENT", "WORKFLOW"]
Environment: TypeAlias = Literal["PRT", "ONLINE"]
ReleaseChannel: TypeAlias = Literal["CURRENT", "STABLE", "GRAY"]
JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]
EffectiveVersions: TypeAlias = tuple[tuple[str, str], ...]

ASSET_KINDS: Final[frozenset[AssetKind]] = frozenset(
    {"SKILL", "ABILITY", "APPLICATION", "COMPONENT", "WORKFLOW"}
)
ENVIRONMENTS: Final[frozenset[Environment]] = frozenset({"PRT", "ONLINE"})


@dataclass(frozen=True, slots=True)
class AssetIdentity:
    """Stable asset identity; draft and release versions are separate values."""

    kind: AssetKind
    key: str


@dataclass(frozen=True, slots=True)
class VersionedAssetIdentity:
    """One immutable retained version of a stable asset identity."""

    asset: AssetIdentity
    version_id: str


class ServingState(TypedDict):
    kind: AssetKind
    key: str
    current: str | None
    stable: str | None
    gray: str | None
    grayUserIds: list[int]
