"""Typed engine-to-management RPC; authority comes only from TrustedContext.

No retries: a timeout does not establish whether business execution occurred.
Dynamic JSON is deeply frozen in returned DTOs and never passes through protobuf double.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import math
from pathlib import Path
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeAlias, TypeVar, Union, cast
from urllib.parse import urlsplit

import grpc
from google.protobuf.message import Message
from a2flow.a2ui.v1 import a2ui_pb2 as ui
from a2flow.a2ui.v1 import a2ui_pb2_grpc as ui_rpc
from a2flow.capability.v1 import capability_pb2 as cap
from a2flow.capability.v1 import capability_pb2_grpc as cap_rpc
from skillweave_contracts import TrustedContext

from .models import ActionRejected

JsonValue: TypeAlias = Union[None, bool, int, float, str, Mapping[str, "JsonValue"], tuple["JsonValue", ...]]
JsonObject: TypeAlias = Mapping[str, JsonValue]
ResponseT = TypeVar("ResponseT", bound=Message)
LOG = logging.getLogger(__name__)


class RpcFailure(ActionRejected):
    """Stable error without server stack, payload, credentials or retry implications."""


def freeze(value: object) -> JsonValue:
    if value is None or type(value) in (bool, int, str):
        return cast(JsonValue, value)
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise RpcFailure("RPC_JSON_INVALID")
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(freeze(item) for item in value)
    raise RpcFailure("RPC_JSON_INVALID")


def thaw(value: JsonValue) -> object:
    """Return a detached ordinary JSON tree for persistence/public projection."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


def _encode(value: object) -> bytes:
    return json.dumps(thaw(freeze(value)), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _decode(value: bytes | str) -> JsonValue:
    try:
        return freeze(json.loads(value))
    except (ValueError, TypeError, UnicodeError):
        raise RpcFailure("RPC_RESPONSE_JSON_INVALID") from None


def _object(value: bytes | str) -> JsonObject:
    result = _decode(value)
    if not isinstance(result, Mapping):
        raise RpcFailure("RPC_RESPONSE_JSON_INVALID")
    return result


def _messages(value: bytes) -> tuple[JsonObject, ...]:
    result = _decode(value)
    if not isinstance(result, tuple) or any(not isinstance(item, Mapping) for item in result):
        raise RpcFailure("RPC_RESPONSE_JSON_INVALID")
    return cast(tuple[JsonObject, ...], result)


@dataclass(frozen=True, slots=True)
class ReleaseIdentity:
    app_code: str
    source_id: str
    digest: str
    app_build_id: str
    environment: str


@dataclass(frozen=True, slots=True)
class CatalogDescriptor:
    protocol_version: str
    catalog_id: str
    catalog_revision: str
    catalog_digest: str


@dataclass(frozen=True, slots=True)
class ActionDescriptor:
    surface_id: str
    component_id: str
    action_name: str
    context_schema: JsonObject


@dataclass(frozen=True, slots=True)
class RuntimeSession:
    token: str
    app_build_id: str
    protocol_version: str
    catalog_id: str
    catalog_revision: str
    catalog_digest: str


@dataclass(frozen=True, slots=True)
class TrustedCard:
    user_id: int
    app_code: str
    params: JsonObject
    snapshot: tuple[JsonObject, ...]

    def __post_init__(self) -> None:
        params = freeze(self.params)
        snapshot = freeze(self.snapshot)
        if (type(self.app_code) is not str or not self.app_code
                or not isinstance(params, Mapping) or not isinstance(snapshot, tuple) or any(
            not isinstance(message, Mapping) for message in snapshot
        )):
            raise RpcFailure("A2UI_CARD_CONTEXT_MISMATCH")
        object.__setattr__(self, "params", params)
        object.__setattr__(self, "snapshot", snapshot)


@dataclass(frozen=True, slots=True)
class ApplicationDescription:
    release: ReleaseIdentity
    params_schema: JsonObject
    interaction_mode: str
    actions: tuple[ActionDescriptor, ...]
    catalog: CatalogDescriptor


@dataclass(frozen=True, slots=True)
class ExecutionSummary:
    binding_id: str
    action_code: str
    success: bool
    capability_version: int
    error_code: str


@dataclass(frozen=True, slots=True)
class ActionExecutionObservation:
    binding_id: str
    action_code: str
    arguments: JsonObject
    result: JsonValue
    capability_success: bool
    business_success: bool | None
    capability_error_code: str | None
    presentation_error_code: str | None


@dataclass(frozen=True, slots=True)
class ComposerDraftEffect:
    type: str
    mode: str
    request_id: str
    text: str


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    release: ReleaseIdentity
    params: JsonObject
    messages: tuple[JsonObject, ...]
    snapshot: tuple[JsonObject, ...]
    executions: tuple[ExecutionSummary, ...]
    actions: tuple[ActionDescriptor, ...]
    complete_interaction: bool
    selected_branch_id: str
    catalog: CatalogDescriptor
    session: RuntimeSession
    interaction_mode: str
    business_success: bool
    action_observation: ActionExecutionObservation | None = None
    composer_draft_effects: tuple[ComposerDraftEffect, ...] = ()


@dataclass(frozen=True, slots=True)
class AbilityDescription:
    asset_key: str
    action_code: str
    capability_version: int
    description: str
    input_schema: JsonObject
    key_output_fields: JsonValue
    resolved_environment: str
    source_id: str
    source_digest: str


@dataclass(frozen=True, slots=True)
class AbilityResult:
    success: bool
    action_code: str
    capability_version: int
    resolved_environment: str
    data: JsonValue
    error_code: str
    message: str
    request_id: str
    source_id: str
    source_digest: str


def _environment(value: int) -> str:
    if value not in (cap.PRT, cap.ONLINE):
        raise RpcFailure("RPC_ENVIRONMENT_MISMATCH")
    return "PRT" if value == cap.PRT else "ONLINE"


def _release(value: ui.ApplicationRelease, owner: TrustedContext, app_code: str) -> ReleaseIdentity:
    result = ReleaseIdentity(value.app_code, value.source_id, value.digest, value.app_build_id,
                             _environment(value.environment))
    if result.environment != owner.environment or result.app_code != app_code or not all(
        (result.source_id, result.digest, result.app_build_id)
    ):
        raise RpcFailure("RPC_RELEASE_MISMATCH")
    return result


def _catalog(value: ui.CatalogDescriptor) -> CatalogDescriptor:
    result = CatalogDescriptor(value.protocol_version, value.catalog_id, value.catalog_revision, value.catalog_digest)
    if not all((result.protocol_version, result.catalog_id, result.catalog_revision, result.catalog_digest)):
        raise RpcFailure("RPC_CATALOG_INVALID")
    return result


def _actions(values: Iterable[ui.ActionDescriptor]) -> tuple[ActionDescriptor, ...]:
    result = tuple(ActionDescriptor(item.surface_id, item.component_id, item.action_name,
                                   _object(item.context_schema_json)) for item in values)
    if any(not all((item.surface_id, item.component_id, item.action_name)) for item in result):
        raise RpcFailure("RPC_ACTION_DESCRIPTOR_INVALID")
    return result


def _mode(value: str) -> str:
    if value not in ("DISPLAY_ONLY", "INTERACTIVE"):
        raise RpcFailure("RPC_INTERACTION_MODE_INVALID")
    return value


class RpcClient:
    """Explicit mTLS channel, or literal loopback for isolated local testing."""

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> RpcClient:
        target = environment.get("A2FLOW_ENGINE_RPC_TARGET", "")
        mode = environment.get("A2FLOW_ENGINE_RPC_MODE", "")
        if not target or mode not in ("LOOPBACK", "MTLS"):
            raise RpcFailure("RPC_CONFIG_REQUIRED")
        try:
            timeout = float(environment.get("A2FLOW_ENGINE_RPC_TIMEOUT_SECONDS", "10"))
            client = environment.get("A2FLOW_ENGINE_RPC_CLIENT", "PC")
            if mode == "LOOPBACK":
                return cls(target, client=client, timeout=timeout, loopback_plaintext=True)
            paths = [environment.get("A2FLOW_ENGINE_RPC_" + name + "_FILE", "") for name in ("CA", "CERT", "KEY")]
            if not all(paths):
                raise RpcFailure("RPC_MTLS_REQUIRED")
            ca, cert, key = (Path(path).read_bytes() for path in paths)
            return cls(target, client=client, timeout=timeout, root_certificates=ca,
                       certificate_chain=cert, private_key=key)
        except (ValueError, OSError):
            raise RpcFailure("RPC_CONFIG_INVALID") from None

    def __init__(self, target: str, *, client: str = "PC", timeout: float = 10.0,
                 loopback_plaintext: bool = False, root_certificates: bytes | None = None,
                 private_key: bytes | None = None, certificate_chain: bytes | None = None) -> None:
        if client not in ("PC", "APP") or not math.isfinite(timeout) or timeout <= 0:
            raise RpcFailure("RPC_CONFIG_INVALID")
        try:
            parsed = urlsplit("//" + target)
            if not parsed.hostname or not parsed.port or parsed.path or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("target")
        except ValueError:
            raise RpcFailure("RPC_CONFIG_INVALID") from None
        options = (("grpc.enable_retries", 0), ("grpc.max_receive_message_length", 2 * 1024 * 1024))
        if loopback_plaintext:
            try:
                if not ipaddress.ip_address(parsed.hostname).is_loopback:
                    raise ValueError("loopback")
            except ValueError:
                raise RpcFailure("RPC_LOOPBACK_REQUIRED") from None
            if any((root_certificates, private_key, certificate_chain)):
                raise RpcFailure("RPC_CONFIG_INVALID")
            self._channel = grpc.insecure_channel(target, options=options)
        else:
            if not all((root_certificates, private_key, certificate_chain)):
                raise RpcFailure("RPC_MTLS_REQUIRED")
            credentials = grpc.ssl_channel_credentials(root_certificates, private_key, certificate_chain)
            self._channel = grpc.secure_channel(target, credentials, options=options)
        self._ui = ui_rpc.A2uiExecutionStub(self._channel)
        self._cap = cap_rpc.CapabilityExecutionStub(self._channel)
        self._client = client
        self._timeout = timeout

    def close(self) -> None:
        self._channel.close()

    def _context(self, owner: TrustedContext, request_id: str) -> cap.ExecutionContext:
        if type(owner) is not TrustedContext or type(request_id) is not str or not request_id or len(request_id) > 200:
            raise RpcFailure("TRUSTED_CONTEXT_REQUIRED")
        return cap.ExecutionContext(user_id=owner.user_id, environment=cap.Environment.Value(owner.environment),
                                    request_id=request_id, client=self._client)

    def _call(self, operation: Callable[..., ResponseT], request: Message) -> ResponseT:
        try:
            return operation(request, timeout=self._timeout, wait_for_ready=False)
        except grpc.RpcError as exception:
            # Status only: provider detail may contain credentials or payloads.
            LOG.warning("RPC transport failed: status=%s", exception.code().name)
            detail = exception.details() or ""
            if exception.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
                raise RpcFailure("RPC_RESOURCE_EXHAUSTED") from None
            if exception.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                raise RpcFailure("RPC_TIMEOUT_OUTCOME_UNKNOWN") from None
            if exception.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
                raise RpcFailure("RPC_AUTHENTICATION_FAILED") from None
            if exception.code() == grpc.StatusCode.FAILED_PRECONDITION and detail.isascii() and all(
                char.isupper() or char.isdigit() or char == "_" for char in detail
            ) and 0 < len(detail) <= 120:
                raise RpcFailure(detail) from None
            raise RpcFailure("RPC_EXECUTION_FAILED") from None

    def describe(self, owner: TrustedContext, app_code: str, request_id: str) -> ApplicationDescription:
        value = self._call(self._ui.Describe, ui.DescribeRequest(context=self._context(owner, request_id), app_code=app_code))
        if value.error_code:
            raise RpcFailure(value.error_code)
        return ApplicationDescription(_release(value.release, owner, app_code), _object(value.params_schema_json),
                                      _mode(value.interaction_mode), _actions(value.actions), _catalog(value.catalog))

    def resolve(self, owner: TrustedContext, asset_key: str, request_id: str) -> AbilityDescription:
        value = self._call(self._cap.Resolve, cap.ResolveRequest(asset_key=asset_key, context=self._context(owner, request_id)))
        environment = _environment(value.resolved_environment)
        if value.asset_key != asset_key or environment != owner.environment or not all((value.source_id, value.source_digest, value.action_code)):
            raise RpcFailure("RPC_RELEASE_MISMATCH")
        return AbilityDescription(value.asset_key, value.action_code, value.capability_version, value.description,
                                  _object(value.input_schema_json), _decode(value.key_output_fields_json), environment,
                                  value.source_id, value.source_digest)

    def activate(self, owner: TrustedContext, app_code: str, params: JsonObject,
                 request_id: str) -> RuntimeResult:
        context = self._context(owner, request_id)
        value = self._call(self._ui.Activate, ui.ActivateRequest(context=context, app_code=app_code,
                           params_json=_encode(params)))
        return self._result(value, owner, app_code)

    def act(self, owner: TrustedContext, card: TrustedCard, action_message: JsonObject, request_id: str,
            *, correlation_id: str) -> RuntimeResult:
        context = self._context(owner, request_id)
        if card.user_id != owner.user_id:
            raise RpcFailure("A2UI_CARD_CONTEXT_MISMATCH")
        trusted = ui.TrustedCard(user_id=card.user_id, app_code=card.app_code,
                                 params_json=_encode(card.params),
                                 snapshot_json=_encode(card.snapshot))
        value = self._call(self._ui.Act, ui.ActRequest(context=context, card=trusted,
                correlation_id=correlation_id, idempotency_key=request_id,
                action_message_json=_encode(action_message)))
        return self._result(value, owner, card.app_code)

    def execute(self, owner: TrustedContext, asset_key: str, arguments: JsonObject,
                request_id: str) -> AbilityResult:
        value = self._call(self._cap.Execute, cap.ExecuteRequest(asset_key=asset_key, context=self._context(owner, request_id),
                    arguments_json=_encode(arguments)))
        environment = _environment(value.resolved_environment)
        if (environment != owner.environment or value.request_id != request_id
                or not value.source_id or not value.source_digest or not value.action_code):
            raise RpcFailure("RPC_RELEASE_MISMATCH")
        return AbilityResult(value.success, value.action_code, value.capability_version, environment, _decode(value.data_json),
                             value.error_code, value.message, value.request_id, value.source_id, value.source_digest)

    def _result(self, value: ui.RuntimeResponse, owner: TrustedContext, app_code: str) -> RuntimeResult:
        if value.error_code:
            raise RpcFailure(value.error_code)
        release = _release(value.release, owner, app_code)
        catalog = _catalog(value.catalog)
        session = RuntimeSession(value.session.token, value.session.app_build_id, value.session.protocol_version,
                                 value.session.catalog_id, value.session.catalog_revision, value.session.catalog_digest)
        if not session.token or (session.app_build_id, session.protocol_version, session.catalog_id,
                session.catalog_revision, session.catalog_digest) != (release.app_build_id, catalog.protocol_version,
                catalog.catalog_id, catalog.catalog_revision, catalog.catalog_digest):
            raise RpcFailure("RPC_SESSION_MISMATCH")
        executions = tuple(ExecutionSummary(item.binding_id, item.action_code, item.success, item.capability_version,
                                            item.error_code) for item in value.executions)
        observation = None
        if value.HasField("action_observation"):
            item = value.action_observation
            observation = ActionExecutionObservation(
                item.binding_id, item.action_code, _object(item.arguments_json),
                _decode(item.result_json), item.capability_success,
                item.business_success if item.HasField("business_success") else None,
                item.capability_error_code or None, item.presentation_error_code or None,
            )
        effects = tuple(
            ComposerDraftEffect(item.type, item.mode, item.request_id, item.text)
            for item in value.composer_draft_effects
        )
        return RuntimeResult(
            release,
            _object(value.params_json),
            _messages(value.messages_json),
            _messages(value.snapshot_json),
            executions,
            _actions(value.actions),
            value.complete_interaction,
            value.selected_branch_id,
            catalog,
            session,
            _mode(value.interaction_mode),
            value.business_success,
            observation,
            effects,
        )
