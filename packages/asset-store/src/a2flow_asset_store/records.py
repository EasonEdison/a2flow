"""Small immutable persistence records; these are not shared wire contracts."""
from dataclasses import dataclass
import hashlib
import json
from skillweave_contracts.user_id import user_id_from_wire

MAX_BYTES = 16 * 1024 * 1024
MAX_ASSETS = 128
KINDS = frozenset({"SKILL", "ABILITY", "APPLICATION", "COMPONENT", "WORKFLOW"})


class AssetError(ValueError):
    """Non-sensitive failure code; never include connection strings or payload."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical(value):
    try:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise AssetError("INVALID_JSON") from None
    if len(data) > MAX_BYTES:
        raise AssetError("BUNDLE_TOO_LARGE")
    return data


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise AssetError("INVALID_FIELDS")


@dataclass(frozen=True)
class Asset:
    kind: str
    key: str
    asset_id: str
    version_id: str
    data: bytes
    content_digest: str

    @property
    def document(self):
        return json.loads(self.data)

    @property
    def definition(self):
        return self.document["definition"]

    @property
    def identity(self):
        return self.kind, self.key, self.version_id


@dataclass(frozen=True)
class Bundle:
    namespace: str
    environment: str
    assets: tuple[Asset, ...]
    serving_data: bytes

    @property
    def serving(self):
        states = json.loads(self.serving_data)
        for state in states:
            state["grayUserIds"] = [user_id_from_wire(user) for user in state["grayUserIds"]]
        return states


@dataclass(frozen=True)
class ResolvedWorkflow:
    data: bytes
    effective_versions: tuple

    @property
    def definition(self):
        return json.loads(self.data)


@dataclass(frozen=True)
class ResolvedAbility:
    data: bytes
    publication_metadata: object
    effective_versions: tuple
    asset_id: str
    version_id: str
    content_digest: str

    @property
    def definition(self):
        return json.loads(self.data)

    @property
    def operation_ref(self):
        return self.publication_metadata.adapter_operation_ref
