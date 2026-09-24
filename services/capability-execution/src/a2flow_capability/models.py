"""Typed execution contracts shared by the capability kernel and transports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, TypeAlias

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1
MAX_TIMEOUT_MS = 120_000
MAX_RESPONSE_BYTES = 5_242_880
TARGET_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
PROTO_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,511}")
FIELD_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
REQUEST_PATH = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*")


class Environment(StrEnum):
    PRT = "PRT"
    ONLINE = "ONLINE"


class JsonKind(StrEnum):
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"


class ContextField(StrEnum):
    USER_ID = "userId"
    CLIENT = "client"
    ENVIRONMENT = "env"


class ExecutionErrorCode(StrEnum):
    TRUSTED_CONTEXT_REQUIRED = "TRUSTED_CONTEXT_REQUIRED"
    CAPABILITY_CLIENT_NOT_SUPPORTED = "CAPABILITY_CLIENT_NOT_SUPPORTED"
    RELEASE_ENVIRONMENT_INVALID = "RELEASE_ENVIRONMENT_INVALID"
    EXECUTION_PLAN_INVALID = "EXECUTION_PLAN_INVALID"
    ARGUMENT_INVALID = "ARGUMENT_INVALID"
    ARGUMENT_TYPE_MISMATCH = "ARGUMENT_TYPE_MISMATCH"
    REQUEST_MAPPING_INVALID = "REQUEST_MAPPING_INVALID"
    TRANSPORT_TIMEOUT = "TRANSPORT_TIMEOUT"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    RESPONSE_SCHEMA_INVALID = "RESPONSE_SCHEMA_INVALID"


class CapabilityExecutionError(RuntimeError):
    """Stable, input-safe execution failure raised before or during transport."""

    def __init__(self, code: ExecutionErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class CapabilityTransportError(RuntimeError):
    """Transport boundary error whose detail must never contain request contents."""

    def __init__(self, code: ExecutionErrorCode, detail: str) -> None:
        if code not in {
            ExecutionErrorCode.REQUEST_MAPPING_INVALID,
            ExecutionErrorCode.RESPONSE_SCHEMA_INVALID,
            ExecutionErrorCode.RESPONSE_TOO_LARGE,
            ExecutionErrorCode.TRANSPORT_TIMEOUT,
            ExecutionErrorCode.TRANSPORT_ERROR,
        }:
            raise ValueError("invalid transport error code")
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class TrustedContext:
    user_id: int
    environment: Environment
    request_id: str
    client: str

    def __post_init__(self) -> None:
        if type(self.user_id) is not int or not MIN_I64 <= self.user_id <= MAX_I64:
            raise CapabilityExecutionError(
                ExecutionErrorCode.TRUSTED_CONTEXT_REQUIRED, "trusted user_id is invalid"
            )
        if not isinstance(self.environment, Environment):
            raise CapabilityExecutionError(
                ExecutionErrorCode.TRUSTED_CONTEXT_REQUIRED, "trusted environment is invalid"
            )
        if type(self.request_id) is not str or not REQUEST_ID.fullmatch(self.request_id):
            raise CapabilityExecutionError(
                ExecutionErrorCode.TRUSTED_CONTEXT_REQUIRED, "trusted request_id is invalid"
            )
        if type(self.client) is not str or not self.client.strip() or len(self.client) > 64:
            raise CapabilityExecutionError(
                ExecutionErrorCode.TRUSTED_CONTEXT_REQUIRED, "trusted client is invalid"
            )


@dataclass(frozen=True, slots=True)
class ObjectProperty:
    name: str
    schema: ValueSchema

    def __post_init__(self) -> None:
        _require_name(self.name, "object property")


@dataclass(frozen=True, slots=True)
class ValueSchema:
    kind: JsonKind
    items: ValueSchema | None = None
    properties: tuple[ObjectProperty, ...] = ()
    required_properties: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, JsonKind):
            raise ValueError("schema kind is invalid")
        if self.kind is JsonKind.ARRAY:
            if self.items is None or self.properties or self.required_properties:
                raise ValueError("array schema requires only items")
            return
        if self.kind is JsonKind.OBJECT:
            if self.items is not None:
                raise ValueError("object schema cannot declare items")
            names = tuple(prop.name for prop in self.properties)
            if len(names) != len(set(names)):
                raise ValueError("object schema property names must be unique")
            if not self.required_properties.issubset(names):
                raise ValueError("required object property is not declared")
            return
        if self.items is not None or self.properties or self.required_properties:
            raise ValueError("scalar schema cannot declare nested members")


@dataclass(frozen=True, slots=True)
class ArgumentDefinition:
    name: str
    schema: ValueSchema
    required: bool = False
    allowed_values: tuple[JsonValue, ...] = ()

    def __post_init__(self) -> None:
        _require_name(self.name, "argument")
        if type(self.required) is not bool:
            raise ValueError("argument required must be boolean")


@dataclass(frozen=True, slots=True)
class RequestMapping:
    argument_name: str
    request_path: str

    def __post_init__(self) -> None:
        _require_name(self.argument_name, "request mapping argument")
        _require_path(self.request_path)


@dataclass(frozen=True, slots=True)
class ContextValueMapping:
    source_value: str
    target_value: str

    def __post_init__(self) -> None:
        if not self.source_value or not self.target_value:
            raise ValueError("context value mapping values cannot be empty")


@dataclass(frozen=True, slots=True)
class ContextMapping:
    request_path: str
    context_field: ContextField
    value_mappings: tuple[ContextValueMapping, ...] = ()

    def __post_init__(self) -> None:
        _require_path(self.request_path)
        if not isinstance(self.context_field, ContextField):
            raise ValueError("context field is invalid")
        sources = tuple(item.source_value for item in self.value_mappings)
        if len(sources) != len(set(sources)):
            raise ValueError("context value mapping source values must be unique")


@dataclass(frozen=True, slots=True)
class ConstantMapping:
    request_path: str
    value: JsonValue

    def __post_init__(self) -> None:
        _require_path(self.request_path)


@dataclass(frozen=True, slots=True)
class PublishedPlan:
    source_id: str
    source_digest: str
    resolved_environment: Environment
    action_code: str
    capability_version: int
    client_type: str
    target_key: str
    service_name: str
    method_name: str
    descriptor_set_base64: str
    context_field: str
    timeout_ms: int
    max_response_bytes: int
    technical_output_schema: JsonObject
    arguments: tuple[ArgumentDefinition, ...] = ()
    request_mappings: tuple[RequestMapping, ...] = ()
    context_mappings: tuple[ContextMapping, ...] = ()
    constant_mappings: tuple[ConstantMapping, ...] = ()
    source_type: str = "GRPC"
    binding_type: str = "GRPC"
    idempotency: str = "NONE"
    response_policy: str = "ORIGINAL"

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id", 256)
        _require_text(self.source_digest, "source_digest", 256)
        _require_text(self.action_code, "action_code", 128)
        _require_text(self.client_type, "client_type", 64)
        if not isinstance(self.resolved_environment, Environment):
            raise ValueError("resolved_environment is invalid")
        if type(self.capability_version) is not int or self.capability_version < 1:
            raise ValueError("capability_version must be positive")
        if not TARGET_KEY.fullmatch(self.target_key):
            raise ValueError("target_key is invalid")
        if not PROTO_NAME.fullmatch(self.service_name):
            raise ValueError("service_name is invalid")
        if not FIELD_NAME.fullmatch(self.method_name):
            raise ValueError("method_name is invalid")
        _require_text(self.descriptor_set_base64, "descriptor_set_base64", 2_800_000)
        if not FIELD_NAME.fullmatch(self.context_field):
            raise ValueError("context_field is invalid")
        if type(self.timeout_ms) is not int or not 1 <= self.timeout_ms <= MAX_TIMEOUT_MS:
            raise ValueError("timeout_ms is invalid")
        if (
            type(self.max_response_bytes) is not int
            or not 1 <= self.max_response_bytes <= MAX_RESPONSE_BYTES
        ):
            raise ValueError("max_response_bytes is invalid")
        if self.source_type != "GRPC" or self.binding_type != "GRPC":
            raise ValueError("only GRPC capability plans are supported")
        if self.idempotency != "NONE":
            raise ValueError("only NONE idempotency is supported")
        if self.response_policy != "ORIGINAL":
            raise ValueError("only ORIGINAL response policy is supported")
        if type(self.technical_output_schema) is not dict:
            raise ValueError("technical_output_schema must be a JSON object")
        names = tuple(argument.name for argument in self.arguments)
        if len(names) != len(set(names)):
            raise ValueError("argument names must be unique")
        declared = set(names)
        for mapping in self.request_mappings:
            if mapping.argument_name not in declared:
                raise ValueError("request mapping references an undeclared argument")
        _require_unique_paths(
            tuple(mapping.request_path for mapping in self.request_mappings)
            + tuple(mapping.request_path for mapping in self.context_mappings)
            + tuple(mapping.request_path for mapping in self.constant_mappings)
        )


@dataclass(frozen=True, slots=True)
class PreparedExecution:
    effective_arguments: JsonObject
    business_request: JsonObject


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    success: bool
    action_code: str
    source_id: str
    source_digest: str
    capability_version: int
    client_type: str
    requested_environment: Environment
    resolved_environment: Environment
    request_id: str
    data: JsonValue = None
    error_code: ExecutionErrorCode | None = None
    message: str | None = None


class CapabilityTransport(Protocol):
    def execute(
        self, plan: PublishedPlan, business: JsonObject, context: TrustedContext
    ) -> JsonValue: ...


def _require_text(value: str, name: str, maximum: int) -> None:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} is invalid")


def _require_name(value: str, description: str) -> None:
    if type(value) is not str or not FIELD_NAME.fullmatch(value):
        raise ValueError(f"{description} name is invalid")


def _require_path(value: str) -> None:
    if type(value) is not str or not REQUEST_PATH.fullmatch(value):
        raise ValueError("request mapping path is invalid")


def _require_unique_paths(paths: tuple[str, ...]) -> None:
    if len(paths) != len(set(paths)):
        raise ValueError("request mappings write the same target more than once")
