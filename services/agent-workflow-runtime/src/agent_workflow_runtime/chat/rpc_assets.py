"""Skill admission and durable Chat cards backed by the deterministic RPC host."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
import json
from typing import Any, cast
from uuid import uuid4

from a2flow_asset_store.java_runtime import PROFILE, is_java_asset
from skillweave_contracts import TrustedContext

from ..application_runtime import PreparedApplication
from ..models import ActionRejected
from ..rpc_client import ApplicationDescription, ReleaseIdentity, RpcClient, RuntimeResult, RuntimeSession, TrustedCard
from .assets import ChatAssets


def plain(value: Any) -> Any:
    """Detach frozen RPC JSON without changing exact integer values."""
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def prepare_result(result: RuntimeResult, version: str) -> PreparedApplication:
    display = {
        "protocolProfile": PROFILE,
        "applicationKey": result.release.app_code,
        "applicationVersion": version,
        "snapshotMessages": plain(result.snapshot),
        "catalog": {"protocolVersion": result.catalog.protocol_version,
                    "catalogId": result.catalog.catalog_id,
                    "catalogRevision": result.catalog.catalog_revision,
                    "catalogDigest": result.catalog.catalog_digest},
        "actions": [{"surfaceId": action.surface_id, "componentId": action.component_id,
                     "actionName": action.action_name, "inputSchema": plain(action.context_schema)}
                    for action in result.actions],
        "data": {}, "components": [],
    }
    return PreparedApplication(result.release.app_code, version,
                               result.interaction_mode == "INTERACTIVE",
                               json.dumps(display, ensure_ascii=False, allow_nan=False))


def runtime_metadata(result: RuntimeResult) -> dict[str, Any]:
    # Persist private session material only in binding_metadata, never display/events.
    return {"release": asdict(result.release), "session": asdict(result.session),
            "params": plain(result.params)}


def trusted_card(owner: TrustedContext, card: dict[str, Any],
                 metadata: dict[str, Any], revision: int) -> TrustedCard:
    private = metadata["rpc"]
    return TrustedCard(user_id=owner.user_id, release=ReleaseIdentity(**private["release"]),
                       session=RuntimeSession(**private["session"]), revision=revision,
                       params=private["params"], snapshot=card["display"]["snapshotMessages"])


class RpcChatAssets(ChatAssets):
    def __init__(self, *, rpc: RpcClient, **kwargs: Any) -> None:
        super().__init__(operation_registry={}, application_validator=lambda _: True,
                         data_validator=lambda _: True, **kwargs)
        self.rpc = rpc

    def admit_skill(self, skill_key: str) -> dict[str, Any]:
        value = super().admit_skill(skill_key)
        admitted = self._require_admission()
        abilities = []
        applications = []
        for key in sorted(admitted.ability_keys):
            record = self._record("ABILITY", key)
            description = self.rpc.resolve(self.owner, record["definition"]["assetKey"],
                                           "contract:" + uuid4().hex)
            if (description.source_id != record["definition"]["sourceId"] or
                    description.source_digest != record["definition"]["sourceDigest"]):
                raise ActionRejected("RESET_REQUIRED")
            abilities.append({"abilityKey": key, "description": description.description,
                              "inputSchema": plain(description.input_schema)})
        for key in sorted(admitted.application_keys):
            _, application = self.application_description(key)
            applications.append({"applicationKey": key, "paramsSchema": plain(application.params_schema),
                                 "interactionMode": application.interaction_mode})
        # Models see only callable business contracts; never transport targets,
        # descriptors, private session tokens or service credentials.
        value["content"]["dependencies"] = {"abilities": abilities, "applications": applications}
        self.check_versions()
        return value

    def _record(self, kind: str, key: str) -> dict[str, Any]:
        admitted = self._require_admission()
        allowed = admitted.ability_keys if kind == "ABILITY" else admitted.application_keys
        if key not in allowed:
            raise ActionRejected(kind + "_NOT_ALLOWED")
        resolved = self._reader.resolve_asset(kind, key, self.owner)
        if not is_java_asset(resolved["definition"]):
            raise ActionRejected("RPC_PUBLICATION_REQUIRED")
        versions = dict(admitted.recorded_versions)
        if any(versions.get(identity) != version for identity, version in resolved["recordedVersions"]):
            raise ActionRejected("RESET_REQUIRED")
        return cast(dict[str, Any], resolved)

    def execute_ability(self, ability_key: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.check_versions()
        record = self._record("ABILITY", ability_key)
        definition = record["definition"]
        result = self.rpc.execute(self.owner, definition["assetKey"], arguments,
                                  definition["sourceId"], definition["sourceDigest"],
                                  "ability:" + uuid4().hex)
        if not result.success:
            raise ActionRejected(result.error_code or "ABILITY_RESULT_NOT_SUCCESS")
        return {"abilityKey": ability_key, "versionId": record["versionId"],
                "output": plain(result.data)}

    def application_description(self, application_key: str) -> tuple[dict[str, Any], ApplicationDescription]:
        record = self._record("APPLICATION", application_key)
        description = self.rpc.describe(self.owner, application_key, "describe:" + uuid4().hex)
        definition = record["definition"]
        if (description.release.source_id != definition["sourceId"] or
                description.release.digest != definition["sourceDigest"]):
            raise ActionRejected("RESET_REQUIRED")
        return record, description

    def render_application(self, application_key: str, data: dict[str, Any],
                           tool_call_id: str) -> dict[str, Any]:
        if type(tool_call_id) is not str or not tool_call_id:
            raise ActionRejected("TOOL_CALL_ID_REQUIRED")
        admitted = self._require_admission()
        with self._render_lock:
            if self._waiting_action is not None:
                raise ActionRejected("INTERACTION_REQUIRED")
            self.check_versions()
            record, description = self.application_description(application_key)
            result = self.rpc.activate(self.owner, application_key, data, description.release,
                                       "render:" + uuid4().hex)
            prepared = prepare_result(result, record["versionId"])
            metadata = {
                "owner": {"userId": self.owner.user_id, "environment": self.owner.environment},
                "conversationId": self.conversation_id, "controlRequestId": self.control_request_id,
                "toolCallId": tool_call_id, "skillKey": admitted.skill_key,
                "recordedVersions": [list(item) for item in admitted.recorded_versions],
                "applicationKey": application_key, "applicationVersion": prepared.application_version,
                "rpc": runtime_metadata(result),
            }
            saved = self._card_sink(prepared, metadata)
            if prepared.interactive:
                self._waiting_action = saved
            return saved
