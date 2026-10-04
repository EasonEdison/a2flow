"""Skill admission and durable Chat cards backed by the deterministic RPC host."""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any, cast
from uuid import uuid4

from a2flow_asset_store.java_runtime import (
    PROFILE,
    is_java_asset,
    validate_java_asset,
)
from skillweave_contracts import TrustedContext

from ..application_runtime import PreparedApplication
from ..models import ActionRejected
from ..rpc_client import (
    ApplicationDescription,
    JsonValue as RpcJsonValue,
    RpcClient,
    RuntimeResult,
    TrustedCard,
)
from .assets import ApplicationContract, ChatAssets, _APPLICATION_USAGE
from .cards import JsonObject, JsonValue

_PRIVATE_OBSERVATION_KEYS = frozenset({
    "authorization", "cookie", "credential", "credentials", "credentialhandle",
    "runtimesessiontoken", "transportauthority", "targetendpoint",
})
_APPLICATION_QUERY_USAGE = (
    "Call query_skill_dependencies with a2uiApplicationCodeList before "
    "render_application."
)


def plain(value: RpcJsonValue) -> JsonValue:
    """Detach frozen RPC JSON without changing exact integer values."""
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return cast(JsonValue, value)


def prepare_result(result: RuntimeResult) -> PreparedApplication:
    version = result.release.app_build_id
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


def rendered_business_state(result: RuntimeResult) -> JsonObject:
    """Project canonical surface DataModels without components or protocol messages."""

    surfaces = []
    for message in result.snapshot:
        update = message.get("updateDataModel")
        if (not isinstance(update, Mapping) or update.get("path") != "/"
                or type(update.get("surfaceId")) is not str):
            continue
        surfaces.append({"surfaceId": update["surfaceId"],
                         "data": plain(update.get("value"))})

    def sanitize(value: JsonValue) -> JsonValue:
        if isinstance(value, Mapping):
            return {key: sanitize(item) for key, item in value.items()
                    if key.replace("_", "").replace("-", "").lower()
                    not in _PRIVATE_OBSERVATION_KEYS}
        if isinstance(value, list):
            return [sanitize(item) for item in value]
        return value

    return {"surfaces": sanitize(surfaces)}


def trusted_card(owner: TrustedContext, card: dict[str, Any],
                 metadata: dict[str, Any]) -> TrustedCard:
    private = metadata["rpc"]
    return TrustedCard(user_id=owner.user_id,
                       app_code=card["display"]["applicationKey"],
                       params=private["params"],
                       snapshot=card["display"]["snapshotMessages"])


class RpcChatAssets(ChatAssets):
    def __init__(self, *, rpc: RpcClient, **kwargs: Any) -> None:
        super().__init__(operation_registry={}, application_validator=lambda _: True,
                         data_validator=lambda _: True, **kwargs)
        self.rpc = rpc
        self._action_descriptions: dict[str, str | None] = {}
        self._render_observations: dict[str, dict[str, Any]] = {}

    def admit_skill(self, skill_key: str) -> dict[str, Any]:
        value = super().admit_skill(skill_key)
        admitted = self._require_admission()
        abilities = []
        application_codes = []
        for key in sorted(admitted.ability_keys):
            record = self._record("ABILITY", key)
            description = self.rpc.resolve(self.owner, record["definition"]["assetKey"],
                                           "contract:" + uuid4().hex)
            abilities.append({"abilityKey": key, "description": description.description,
                              "inputSchema": plain(description.input_schema)})
            current = self._action_descriptions.get(description.action_code)
            if current is None and description.action_code not in self._action_descriptions:
                self._action_descriptions[description.action_code] = description.description
            elif current != description.description:
                self._action_descriptions[description.action_code] = None
        for key in sorted(admitted.application_keys):
            application_codes.append(key)
        # Models see only callable business contracts; never transport targets,
        # descriptors, private session tokens or service credentials.
        value["content"]["dependencies"] = {
            "abilities": abilities,
            "applications": {
                "appCodes": application_codes,
                "usage": _APPLICATION_QUERY_USAGE,
            },
        }
        return value

    def action_description(self, action_code: str) -> str | None:
        """Return only an unambiguous description from the admitted published Ability."""

        return self._action_descriptions.get(action_code)

    def action_descriptions(self) -> dict[str, str | None]:
        """Snapshot admitted Ability descriptions before business dispatch."""

        return dict(self._action_descriptions)

    def render_observation(self, card_id: str) -> dict[str, Any] | None:
        value = self._render_observations.get(card_id)
        return None if value is None else cast(dict[str, Any], plain(value))

    def _record(self, kind: str, key: str) -> dict[str, Any]:
        admitted = self.refresh_admission()
        allowed = admitted.ability_keys if kind == "ABILITY" else admitted.application_keys
        if key not in allowed:
            raise ActionRejected(kind + "_NOT_ALLOWED")
        resolved = self._reader.resolve_asset(kind, key, self.owner)
        if not is_java_asset(resolved["definition"]):
            raise ActionRejected("RPC_PUBLICATION_REQUIRED")
        return cast(dict[str, Any], resolved)

    def execute_ability(self, ability_key: str, arguments: dict[str, Any]) -> dict[str, Any]:
        record = self._record("ABILITY", ability_key)
        definition = record["definition"]
        result = self.rpc.execute(self.owner, definition["assetKey"], arguments,
                                  "ability:" + uuid4().hex)
        if not result.success:
            raise ActionRejected(result.error_code or "ABILITY_RESULT_NOT_SUCCESS")
        return {"abilityKey": ability_key, "versionId": record["versionId"],
                "output": plain(result.data)}

    def application_description(self, application_key: str) -> tuple[dict[str, Any], ApplicationDescription]:
        record = self._record("APPLICATION", application_key)
        description = self.rpc.describe(self.owner, application_key, "describe:" + uuid4().hex)
        return record, description

    def _application_contract(self, application_key: str) -> ApplicationContract:
        """Project only the model-facing contract from one admitted release."""

        record, runtime = self.application_description(application_key)
        build = validate_java_asset(
            "APPLICATION", application_key, record["definition"],
        )
        description = build.get("description")
        published_schema = plain(build.get("paramsSchema"))
        runtime_schema = plain(runtime.params_schema)
        if (
            type(description) is not str
            or type(published_schema) is not dict
            or published_schema != runtime_schema
        ):
            raise ActionRejected("APPLICATION_CONTRACT_INVALID")
        return {
            "appCode": application_key,
            "description": description,
            "usage": _APPLICATION_USAGE,
            "paramsSchema": runtime_schema,
        }

    def render_application(self, application_key: str, data: dict[str, Any],
                           tool_call_id: str) -> dict[str, Any]:
        if type(tool_call_id) is not str or not tool_call_id:
            raise ActionRejected("TOOL_CALL_ID_REQUIRED")
        admitted = self._require_admission()
        with self._render_lock:
            if self._waiting_action is not None:
                raise ActionRejected("INTERACTION_REQUIRED")
            _, description = self.application_description(application_key)
            result = self.rpc.activate(self.owner, application_key, data,
                                       "render:" + uuid4().hex)
            prepared = prepare_result(result)
            metadata = {
                "owner": {"userId": self.owner.user_id, "environment": self.owner.environment},
                "conversationId": self.conversation_id, "controlRequestId": self.control_request_id,
                "toolCallId": tool_call_id, "skillKey": admitted.skill_key,
                "applicationKey": application_key, "applicationVersion": prepared.application_version,
                "rpc": runtime_metadata(result),
                "observation": {"arguments": rendered_business_state(result)},
            }
            saved = self._card_sink(prepared, metadata)
            self._render_observations[saved["cardId"]] = {
                "cardId": saved["cardId"], "applicationKey": application_key,
                "arguments": rendered_business_state(result),
            }
            if prepared.interactive:
                self._waiting_action = saved
            return saved
