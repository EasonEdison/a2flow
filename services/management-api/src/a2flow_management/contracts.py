"""Management values. Trusted context is constructed only by the Host."""
from dataclasses import dataclass
import hashlib
import json
import re
from skillweave_contracts.user_id import require_user_id, user_id_to_wire

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}")
_KINDS = frozenset({"SKILL", "ABILITY", "APPLICATION", "COMPONENT", "WORKFLOW"})
_MAX_BYTES = 8 * 1024 * 1024


class ManagementError(ValueError):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def canonical(value):
    try:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ManagementError("INVALID_JSON") from None
    if len(data) > _MAX_BYTES:
        raise ManagementError("DOCUMENT_TOO_LARGE", 413)
    return data


def identifier(value, code="INVALID_IDENTIFIER"):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ManagementError(code)
    return value


def user_identifier(value, code="INVALID_TRUSTED_USER"):
    try:
        return require_user_id(value)
    except ValueError:
        raise ManagementError(code) from None


@dataclass(frozen=True)
class TrustedManagementContext:
    user_id: int
    environment: str
    roles: frozenset[str]

    def __post_init__(self):
        user_identifier(self.user_id)
        if self.environment not in {"PRT", "ONLINE"}:
            raise ManagementError("INVALID_TRUSTED_ENVIRONMENT")
        if type(self.roles) is not frozenset or not self.roles <= {"ADMIN", "USER"}:
            raise ManagementError("INVALID_TRUSTED_ROLES")


def require_admin(context):
    if type(context) is not TrustedManagementContext:
        raise ManagementError("TRUSTED_CONTEXT_REQUIRED", 401)
    if "ADMIN" not in context.roles:
        raise ManagementError("ADMIN_REQUIRED", 403)
    return context


def require_reader(context):
    if type(context) is not TrustedManagementContext:
        raise ManagementError("TRUSTED_CONTEXT_REQUIRED", 401)
    if not context.roles.intersection({"ADMIN", "USER"}):
        raise ManagementError("READ_ROLE_REQUIRED", 403)
    return context


@dataclass(frozen=True)
class ManagedDraft:
    kind: str
    key: str
    revision: int
    data: bytes
    content_digest: str
    updated_by: int

    def __post_init__(self):
        user_identifier(self.updated_by)

    @classmethod
    def create(cls, kind, key, revision, document, updated_by):
        if kind not in _KINDS:
            raise ManagementError("INVALID_ASSET_KIND")
        identifier(key, "INVALID_ASSET_KEY")
        user_identifier(updated_by)
        if type(revision) is not int or revision < 0:
            raise ManagementError("INVALID_DRAFT_REVISION")
        data = canonical(document)
        return cls(kind, key, revision, data,
                   "sha256:" + hashlib.sha256(data).hexdigest(), updated_by)

    @property
    def document(self):
        return json.loads(self.data)

    def to_mapping(self):
        return {"kind": self.kind, "key": self.key, "revision": self.revision,
                "document": self.document, "contentDigest": self.content_digest,
                "updatedBy": user_id_to_wire(self.updated_by)}


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    issues: tuple[dict, ...]
    normalized_data: bytes | None = None

    @classmethod
    def success(cls, normalized):
        return cls(True, (), canonical(normalized))

    @classmethod
    def failure(cls, code, path="/"):
        identifier(code, "INVALID_ISSUE_CODE")
        return cls(False, ({"code": code, "path": path},))

    @property
    def normalized(self):
        return None if self.normalized_data is None else json.loads(self.normalized_data)

    def to_mapping(self):
        value = {"valid": self.valid, "issues": list(self.issues)}
        if self.normalized_data is not None:
            value["normalized"] = self.normalized
        return value


@dataclass(frozen=True)
class PublicationTarget:
    environment: str
    version_id: str
    channel: str
    gray_user_ids: tuple[int, ...] = ()

    def __post_init__(self):
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
        if len(self.gray_user_ids) > 1024 or len(set(self.gray_user_ids)) != len(self.gray_user_ids):
            raise ManagementError("INVALID_GRAY_USERS")


@dataclass(frozen=True)
class PublicationPlan:
    kind: str
    key: str
    draft_revision: int
    target: PublicationTarget
    candidate_data: bytes
    content_digest: str

    @classmethod
    def create(cls, kind, key, revision, target, candidate):
        data = canonical(candidate)
        return cls(kind, key, revision, target, data,
                   "sha256:" + hashlib.sha256(data).hexdigest())

    @property
    def candidate(self):
        return json.loads(self.candidate_data)

    def to_mapping(self):
        return {"kind": self.kind, "key": self.key,
                "draftRevision": self.draft_revision,
                "target": {"environment": self.target.environment,
                           "versionId": self.target.version_id,
                           "channel": self.target.channel,
                           "grayUserIds": [user_id_to_wire(user) for user in self.target.gray_user_ids]},
                "candidate": self.candidate, "contentDigest": self.content_digest}
