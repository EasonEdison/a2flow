"""Management values. Trusted context is constructed only by the Host."""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal, NotRequired, Self, TypeAlias, TypedDict, cast

from skillweave_contracts.user_id import require_user_id, user_id_to_wire

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}")
_KINDS = frozenset({"SKILL", "ABILITY", "APPLICATION", "COMPONENT", "WORKFLOW"})
_MAX_BYTES = 8 * 1024 * 1024

AssetKind: TypeAlias = Literal["SKILL", "ABILITY", "APPLICATION", "COMPONENT", "WORKFLOW"]
Environment: TypeAlias = Literal["PRT", "ONLINE"]
ReleaseChannel: TypeAlias = Literal["CURRENT", "STABLE", "GRAY"]
Role: TypeAlias = Literal["ADMIN", "USER"]
JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class ValidationIssue(TypedDict):
    code: str
    path: str


class ValidationReportMapping(TypedDict):
    valid: bool
    issues: list[ValidationIssue]
    normalized: NotRequired[JsonValue]


class PublicationTargetMapping(TypedDict):
    environment: Environment
    versionId: str
    channel: ReleaseChannel
    grayUserIds: list[str]


class PublicationPlanMapping(TypedDict):
    kind: AssetKind
    key: str
    draftRevision: int
    target: PublicationTargetMapping
    candidate: JsonObject
    contentDigest: str


class ManagementError(ValueError):
    def __init__(self, code: str, status: int = 400) -> None:
        self.code, self.status = code, status
        super().__init__(code)


def canonical(value: JsonValue) -> bytes:
    try:
        data = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ManagementError("INVALID_JSON") from None
    if len(data) > _MAX_BYTES:
        raise ManagementError("DOCUMENT_TOO_LARGE", 413)
    return data


def identifier(value: object, code: str = "INVALID_IDENTIFIER") -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ManagementError(code)
    return value


def user_identifier(value: object, code: str = "INVALID_TRUSTED_USER") -> int:
    try:
        return require_user_id(value)
    except ValueError:
        raise ManagementError(code) from None


@dataclass(frozen=True)
class TrustedManagementContext:
    user_id: int
    environment: Environment
    roles: frozenset[Role]

    def __post_init__(self) -> None:
        user_identifier(self.user_id)
        if self.environment not in {"PRT", "ONLINE"}:
            raise ManagementError("INVALID_TRUSTED_ENVIRONMENT")
        if type(self.roles) is not frozenset or not self.roles <= {"ADMIN", "USER"}:
            raise ManagementError("INVALID_TRUSTED_ROLES")


def require_admin(context: object) -> TrustedManagementContext:
    if type(context) is not TrustedManagementContext:
        raise ManagementError("TRUSTED_CONTEXT_REQUIRED", 401)
    if "ADMIN" not in context.roles:
        raise ManagementError("ADMIN_REQUIRED", 403)
    return context


def require_reader(context: object) -> TrustedManagementContext:
    if type(context) is not TrustedManagementContext:
        raise ManagementError("TRUSTED_CONTEXT_REQUIRED", 401)
    if not context.roles.intersection({"ADMIN", "USER"}):
        raise ManagementError("READ_ROLE_REQUIRED", 403)
    return context


@dataclass(frozen=True)
class ManagedDraft:
    kind: AssetKind
    key: str
    revision: int
    data: bytes
    content_digest: str
    updated_by: int

    def __post_init__(self) -> None:
        user_identifier(self.updated_by)

    @classmethod
    def create(
        cls,
        kind: str,
        key: str,
        revision: int,
        document: JsonObject,
        updated_by: int,
    ) -> Self:
        if kind not in _KINDS:
            raise ManagementError("INVALID_ASSET_KIND")
        identifier(key, "INVALID_ASSET_KEY")
        user_identifier(updated_by)
        if type(revision) is not int or revision < 0:
            raise ManagementError("INVALID_DRAFT_REVISION")
        data = canonical(document)
        return cls(
            cast(AssetKind, kind),
            key,
            revision,
            data,
            "sha256:" + hashlib.sha256(data).hexdigest(),
            updated_by,
        )

    @property
    def document(self) -> JsonObject:
        return cast(JsonObject, json.loads(self.data))

    def to_mapping(self) -> JsonObject:
        return {
            "kind": self.kind,
            "key": self.key,
            "revision": self.revision,
            "document": self.document,
            "contentDigest": self.content_digest,
            "updatedBy": user_id_to_wire(self.updated_by),
        }


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    issues: tuple[ValidationIssue, ...]
    normalized_data: bytes | None = None

    @classmethod
    def success(cls, normalized: JsonValue) -> Self:
        return cls(True, (), canonical(normalized))

    @classmethod
    def failure(cls, code: str, path: str = "/") -> Self:
        identifier(code, "INVALID_ISSUE_CODE")
        return cls(False, ({"code": code, "path": path},))

    @property
    def normalized(self) -> JsonValue:
        return (
            None
            if self.normalized_data is None
            else cast(JsonValue, json.loads(self.normalized_data))
        )

    def to_mapping(self) -> ValidationReportMapping:
        value: ValidationReportMapping = {"valid": self.valid, "issues": list(self.issues)}
        if self.normalized_data is not None:
            value["normalized"] = self.normalized
        return value


@dataclass(frozen=True)
class PublicationTarget:
    environment: Environment
    version_id: str
    channel: ReleaseChannel
    gray_user_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if type(self.gray_user_ids) is not tuple:
            raise ManagementError("INVALID_GRAY_USERS")
        identifier(self.version_id, "INVALID_VERSION")
        if self.environment == "PRT":
            if self.channel != "CURRENT" or self.gray_user_ids:
                raise ManagementError("INVALID_PRT_TARGET")
        elif self.environment == "ONLINE":
            if self.channel not in {"STABLE", "GRAY"}:
                raise ManagementError("INVALID_ONLINE_TARGET")
        else:
            raise ManagementError("INVALID_TARGET_ENVIRONMENT")
        if self.channel == "GRAY" and not self.gray_user_ids:
            raise ManagementError("GRAY_USERS_REQUIRED")
        if self.channel != "GRAY" and self.gray_user_ids:
            raise ManagementError("GRAY_USERS_NOT_ALLOWED")
        for user_id in self.gray_user_ids:
            user_identifier(user_id, "INVALID_GRAY_USER")
        if len(self.gray_user_ids) > 1024 or len(set(self.gray_user_ids)) != len(
            self.gray_user_ids
        ):
            raise ManagementError("INVALID_GRAY_USERS")

    def to_mapping(self) -> PublicationTargetMapping:
        return {
            "environment": self.environment,
            "versionId": self.version_id,
            "channel": self.channel,
            "grayUserIds": [user_id_to_wire(user) for user in self.gray_user_ids],
        }


@dataclass(frozen=True)
class PublicationPlan:
    kind: AssetKind
    key: str
    draft_revision: int
    target: PublicationTarget
    candidate_data: bytes
    content_digest: str

    @classmethod
    def create(
        cls,
        kind: AssetKind,
        key: str,
        revision: int,
        target: PublicationTarget,
        candidate: JsonObject,
    ) -> Self:
        data = canonical(candidate)
        return cls(
            kind,
            key,
            revision,
            target,
            data,
            "sha256:" + hashlib.sha256(data).hexdigest(),
        )

    @property
    def candidate(self) -> JsonObject:
        return cast(JsonObject, json.loads(self.candidate_data))

    def to_mapping(self) -> PublicationPlanMapping:
        return {
            "kind": self.kind,
            "key": self.key,
            "draftRevision": self.draft_revision,
            "target": self.target.to_mapping(),
            "candidate": self.candidate,
            "contentDigest": self.content_digest,
        }
