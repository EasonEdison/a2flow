"""Owner-scoped immutable execution configurations, separate from M publications."""

from __future__ import annotations

import json
from collections.abc import Callable
from hashlib import sha256
from typing import Any, cast

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from skillweave_contracts import TrustedContext

from .java_runtime import is_java_asset
from .reader import AssetReader, owner_context
from .records import AssetError, ResolvedWorkflow, canonical, digest
from .validation import BundleValidator
from .validation import environment as valid_environment
from .validation import namespace as valid_namespace

PREFIX = "personal-wf-"
INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["requirement"],
    "properties": {"requirement": {"type": "string", "minLength": 1, "maxLength": 2000}},
}
DDL = """CREATE TABLE IF NOT EXISTS personal_workflow_definitions (
 namespace TEXT NOT NULL, environment TEXT NOT NULL CHECK(environment IN ('PRT','ONLINE')),
 user_id BIGINT NOT NULL, workflow_key TEXT NOT NULL, conversation_id TEXT NOT NULL,
 tool_call_id TEXT NOT NULL, request_digest TEXT NOT NULL, document JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(namespace,environment,user_id,workflow_key),
 UNIQUE(namespace,environment,user_id,conversation_id,tool_call_id))"""


def _text(value: object, limit: int, code: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise AssetError(code)
    return value


def workflow_key(namespace: str, owner: TrustedContext, conversation: str, call: str) -> str:
    payload = canonical([namespace, owner.environment, owner.user_id, conversation, call])
    return PREFIX + sha256(payload).hexdigest()


def catalog_entry(document: dict[str, Any]) -> dict[str, Any]:
    definition = document["definition"]
    nodes = []
    for node in definition["nodes"]:
        capability = node.get("type") == "BUSINESS_CAPABILITY"
        reference = "abilityKey" if capability else "skillKey"
        item = {
            "nodeId": node["nodeId"],
            "type": "BUSINESS_CAPABILITY" if capability else "SKILL",
            reference: node[reference],
        }
        if node.get("displayName"):
            item["displayName"] = node["displayName"]
        nodes.append(item)
    return {
        "definitionKey": definition["definitionKey"],
        "name": definition["displayName"],
        "source": "PERSONAL",
        "defaultRequirement": document["defaultRequirement"],
        "nodes": nodes,
        "inputSchema": json.loads(json.dumps(INPUT_SCHEMA)),
    }


class PersonalWorkflowRepository:
    """One transaction binds a stable trusted request identity to an immutable definition."""

    def __init__(
        self,
        connection_factory: Callable[[], Connection[dict[str, Any]]],
        *,
        namespace: str,
        environment: str,
        validator: BundleValidator,
    ) -> None:
        self.connection_factory = connection_factory
        self.namespace = valid_namespace(namespace)
        self.environment = valid_environment(environment)
        self.validator = validator

    def install(self) -> None:
        """Explicit host migration only. Normal startup and reads never create tables."""
        with self.connection_factory() as connection:
            connection.execute(DDL)

    def _owner(self, context: object) -> TrustedContext:
        owner = cast(TrustedContext, owner_context(context))
        if owner.environment != self.environment:
            raise AssetError("ENVIRONMENT_MISMATCH")
        return owner

    def read(self, owner: object, key: str) -> dict[str, Any]:
        trusted = self._owner(owner)
        if not isinstance(key, str) or not key.startswith(PREFIX):
            raise AssetError("PERSONAL_WORKFLOW_NOT_FOUND")
        with (
            self.connection_factory() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                "SELECT document FROM personal_workflow_definitions "
                "WHERE namespace=%s AND environment=%s AND user_id=%s AND workflow_key=%s",
                (self.namespace, self.environment, trusted.user_id, key),
            )
            row = cursor.fetchone()
        if row is None:
            raise AssetError("PERSONAL_WORKFLOW_NOT_FOUND")
        return dict(row["document"])

    def list(self, owner: object) -> tuple[dict[str, Any], ...]:
        trusted = self._owner(owner)
        with (
            self.connection_factory() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                "SELECT document FROM personal_workflow_definitions "
                "WHERE namespace=%s AND environment=%s AND user_id=%s "
                "ORDER BY created_at,workflow_key",
                (self.namespace, self.environment, trusted.user_id),
            )
            return tuple(dict(row["document"]) for row in cursor.fetchall())

    def replay(
        self,
        owner: object,
        conversation_id: str,
        tool_call_id: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        trusted = self._owner(owner)
        key = workflow_key(self.namespace, trusted, conversation_id, tool_call_id)
        try:
            value = self.read(trusted, key)
        except AssetError as error:
            if error.code == "PERSONAL_WORKFLOW_NOT_FOUND":
                return None
            raise
        if value["requestDigest"] != request_digest:
            raise AssetError("PERSONAL_WORKFLOW_REQUEST_CONFLICT")
        return value

    def create(
        self,
        owner: object,
        conversation_id: str,
        tool_call_id: str,
        definition: dict[str, Any],
        default_requirement: str,
    ) -> dict[str, Any]:
        trusted = self._owner(owner)
        _text(conversation_id, 256, "INVALID_CONVERSATION_ID")
        _text(tool_call_id, 256, "INVALID_TOOL_CALL_ID")
        _text(default_requirement, 2000, "PERSONAL_WORKFLOW_REQUIREMENT_INVALID")
        key = workflow_key(self.namespace, trusted, conversation_id, tool_call_id)
        if definition.get("definitionKey") != key:
            raise AssetError("PERSONAL_WORKFLOW_KEY_CONFLICT")
        self.validator.validate_definition("WORKFLOW", key, definition)
        _text(definition.get("displayName"), 200, "PERSONAL_WORKFLOW_NAME_INVALID")
        _text(definition.get("summaryPrompt"), 4096, "INVALID_WORKFLOW_SUMMARY_PROMPT")
        request_digest = digest(
            canonical({"definition": definition, "defaultRequirement": default_requirement})
        )
        document = {
            "definition": definition,
            "defaultRequirement": default_requirement,
            "requestDigest": request_digest,
        }
        try:
            with self.connection_factory() as connection:
                connection.execute(
                    "INSERT INTO personal_workflow_definitions "
                    "(namespace,environment,user_id,workflow_key,conversation_id,tool_call_id,"
                    "request_digest,document) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (namespace,environment,user_id,conversation_id,tool_call_id) "
                    "DO NOTHING",
                    (
                        self.namespace,
                        self.environment,
                        trusted.user_id,
                        key,
                        conversation_id,
                        tool_call_id,
                        request_digest,
                        Jsonb(document),
                    ),
                )
        except Exception:
            # A failed response is not proof that COMMIT failed. Read this exact identity;
            # never repeat INSERT or create under another request/key.
            try:
                prior = self.replay(trusted, conversation_id, tool_call_id, request_digest)
            except AssetError:
                raise
            except Exception:
                raise AssetError("PERSONAL_WORKFLOW_SAVE_UNCONFIRMED") from None
            if prior is not None:
                return prior
            raise AssetError("PERSONAL_WORKFLOW_SAVE_UNCONFIRMED") from None
        try:
            saved = self.replay(trusted, conversation_id, tool_call_id, request_digest)
        except AssetError:
            raise
        except Exception:
            raise AssetError("PERSONAL_WORKFLOW_SAVE_UNCONFIRMED") from None
        if saved is None:
            raise AssetError("PERSONAL_WORKFLOW_SAVE_UNCONFIRMED")
        return saved


class PersonalWorkflowReader:
    """Explicit personal-key routing; misses and owner mismatches never fall back."""

    def __init__(
        self, base_reader: AssetReader, personal_repository: PersonalWorkflowRepository
    ) -> None:
        if (
            base_reader.namespace != personal_repository.namespace
            or base_reader.repository.environment != personal_repository.environment
        ):
            raise AssetError("DESTINATION_MISMATCH")
        self.base_reader = base_reader
        self.personal_repository = personal_repository
        self.namespace = personal_repository.namespace

    def __getattr__(self, name: str) -> object:
        return getattr(self.base_reader, name)

    def list_workflows(self, owner: object) -> tuple[dict[str, Any], ...]:
        trusted = self.personal_repository._owner(owner)
        presets = []
        for entry in self.base_reader.list_workflows(trusted):
            if entry["definitionKey"].startswith(PREFIX):
                raise AssetError("PERSONAL_WORKFLOW_RESERVED_KEY")
            presets.append({**entry, "source": "PRESET"})
        return (*presets, *(catalog_entry(d) for d in self.personal_repository.list(trusted)))

    def read_personal_workflow(self, owner: object, key: str) -> dict[str, Any]:
        document = self.personal_repository.read(owner, key)
        return {**catalog_entry(document), "definition": document["definition"]}

    def _dependencies(
        self,
        owner: TrustedContext,
        definition: dict[str, Any],
    ) -> tuple[list[dict[str, str]], tuple[tuple[str, str], ...]]:
        dependencies = sorted(
            {
                ("ABILITY", n["abilityKey"])
                if n.get("type") == "BUSINESS_CAPABILITY"
                else ("SKILL", n["skillKey"])
                for n in definition["nodes"]
            }
        )
        versions: dict[str, str] = {}
        for kind, key in dependencies:
            record = self.base_reader.resolve_asset(kind, key, owner)
            if kind == "ABILITY" and not is_java_asset(record["definition"]):
                raise AssetError("RPC_PUBLICATION_REQUIRED")
            for identity, version in record["recordedVersions"]:
                if identity in versions and versions[identity] != version:
                    raise AssetError("VERSION_CONFLICT")
                versions[identity] = version
        return (
            [{"kind": kind, "key": key} for kind, key in dependencies],
            tuple(sorted(versions.items())),
        )

    def create_personal_workflow(
        self,
        owner: object,
        conversation_id: str,
        tool_call_id: str,
        *,
        name: str,
        default_requirement: str,
        nodes: list[dict[str, Any]],
        summary_prompt: str,
    ) -> dict[str, Any]:
        trusted = self.personal_repository._owner(owner)
        _text(conversation_id, 256, "INVALID_CONVERSATION_ID")
        _text(tool_call_id, 256, "INVALID_TOOL_CALL_ID")
        key = workflow_key(self.namespace, trusted, conversation_id, tool_call_id)
        if (
            type(nodes) is not list
            or not 1 <= len(nodes) <= 8
            or any(type(node) is not dict or "nodeId" not in node for node in nodes)
        ):
            raise AssetError("UNSUPPORTED_WORKFLOW")
        definition = {
            "definitionKey": key,
            "displayName": name,
            "entryNodeId": nodes[0]["nodeId"],
            "nodes": nodes,
            "summaryPrompt": summary_prompt,
        }
        self.personal_repository.validator.validate_definition("WORKFLOW", key, definition)
        _text(name, 200, "PERSONAL_WORKFLOW_NAME_INVALID")
        _text(default_requirement, 2000, "PERSONAL_WORKFLOW_REQUIREMENT_INVALID")
        _text(summary_prompt, 4096, "INVALID_WORKFLOW_SUMMARY_PROMPT")
        request_digest = digest(
            canonical({"definition": definition, "defaultRequirement": default_requirement})
        )
        prior = self.personal_repository.replay(
            trusted,
            conversation_id,
            tool_call_id,
            request_digest,
        )
        if prior is not None:
            return catalog_entry(prior)
        self._dependencies(trusted, definition)
        saved = self.personal_repository.create(
            trusted,
            conversation_id,
            tool_call_id,
            definition,
            default_requirement,
        )
        return catalog_entry(saved)

    def resolve_asset(self, kind: str, key: str, context: object) -> dict[str, Any]:
        if kind != "WORKFLOW" or not key.startswith(PREFIX):
            return cast(dict[str, Any], self.base_reader.resolve_asset(kind, key, context))
        owner = self.personal_repository._owner(context)
        document = self.personal_repository.read(owner, key)
        definition = document["definition"]
        self.personal_repository.validator.validate_definition("WORKFLOW", key, definition)
        dependencies, versions = self._dependencies(owner, definition)
        content_digest = digest(canonical(document))
        version = "personal-" + content_digest.removeprefix("sha256:")
        return {
            "kind": "WORKFLOW",
            "key": key,
            "assetId": key,
            "versionId": version,
            "contentDigest": content_digest,
            "definition": definition,
            "dependencies": dependencies,
            "selection": "PERSONAL",
            "recordedVersions": tuple(sorted((("WORKFLOW:" + key, version), *versions))),
        }

    def list_assets(self, kind: str, owner: object) -> tuple[dict[str, Any], ...]:
        if kind != "WORKFLOW":
            return cast(tuple[dict[str, Any], ...], self.base_reader.list_assets(kind, owner))
        rows = list(self.base_reader.list_assets(kind, owner))
        if any(row["key"].startswith(PREFIX) for row in rows):
            raise AssetError("PERSONAL_WORKFLOW_RESERVED_KEY")
        for document in self.personal_repository.list(owner):
            record = self.resolve_asset("WORKFLOW", document["definition"]["definitionKey"], owner)
            rows.append(
                {
                    key: record[key]
                    for key in (
                        "kind",
                        "key",
                        "assetId",
                        "versionId",
                        "contentDigest",
                        "selection",
                    )
                }
            )
        return tuple(sorted(rows, key=lambda row: row["key"]))

    def asset_exists(self, kind: str, key: str, context: object) -> bool:
        if kind != "WORKFLOW" or not key.startswith(PREFIX):
            return cast(bool, self.base_reader.asset_exists(kind, key, context))
        try:
            self.personal_repository.read(context, key)
            return True
        except AssetError as error:
            if error.code == "PERSONAL_WORKFLOW_NOT_FOUND":
                return False
            raise

    def resolve_workflow(self, definition_key: str, owner: object) -> ResolvedWorkflow:
        if not definition_key.startswith(PREFIX):
            return cast(ResolvedWorkflow, self.base_reader.resolve_workflow(definition_key, owner))
        value = self.resolve_asset("WORKFLOW", definition_key, owner)
        return ResolvedWorkflow(canonical(value["definition"]), value["recordedVersions"])

    def versions(self, owner: object, definition_key: str) -> tuple[tuple[str, str], ...]:
        return self.resolve_workflow(definition_key, owner).effective_versions
