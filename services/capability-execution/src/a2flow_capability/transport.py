"""Registered unary Protobuf transport; no model-selected addresses or reflection."""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import grpc
from a2flow.capability.v1 import capability_pb2 as cap
from google.protobuf import descriptor_pb2, descriptor_pool, json_format, message_factory
from google.protobuf.descriptor import Descriptor, MethodDescriptor
from google.protobuf.message import DecodeError, Message
from jsonschema import Draft7Validator

from .models import (
    CapabilityTransportError,
    ExecutionErrorCode,
    JsonObject,
    JsonValue,
    TrustedContext,
)


class RpcPlan(Protocol):
    @property
    def target_key(self) -> str: ...
    @property
    def service_name(self) -> str: ...
    @property
    def method_name(self) -> str: ...
    @property
    def descriptor_set_base64(self) -> str: ...
    @property
    def context_field(self) -> str: ...
    @property
    def timeout_ms(self) -> int: ...
    @property
    def max_response_bytes(self) -> int: ...
    @property
    def technical_output_schema(self) -> JsonObject: ...


class TransportError(CapabilityTransportError):
    """Stable boundary error without credential, payload or peer exception details."""

    def __init__(self, detail: str, code: str = "TRANSPORT_ERROR") -> None:
        super().__init__(ExecutionErrorCode(code), detail)


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    loopback_plaintext: bool = False
    trust_cert_file: Path | None = None
    client_cert_file: Path | None = None
    client_key_file: Path | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9.-]+", self.host):
            raise TransportError("INVALID_TARGET_HOST")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise TransportError("INVALID_TARGET_PORT")
        if type(self.loopback_plaintext) is not bool:
            raise TransportError("INVALID_TARGET_MODE")
        if self.loopback_plaintext:
            if self.host != "127.0.0.1":
                raise TransportError("PLAINTEXT_REQUIRES_LITERAL_LOOPBACK")
        elif not all((self.trust_cert_file, self.client_cert_file, self.client_key_file)):
            raise TransportError("MTLS_CREDENTIALS_REQUIRED")

    def open(self, max_response_bytes: int) -> grpc.Channel:
        options = (
            ("grpc.enable_retries", 0),
            ("grpc.max_send_message_length", 1024 * 1024),
            ("grpc.max_receive_message_length", max_response_bytes),
        )
        target = f"{self.host}:{self.port}"
        if self.loopback_plaintext:
            return grpc.insecure_channel(target, options=options)
        assert self.trust_cert_file and self.client_cert_file and self.client_key_file
        credentials = grpc.ssl_channel_credentials(
            self.trust_cert_file.read_bytes(),
            self.client_key_file.read_bytes(),
            self.client_cert_file.read_bytes(),
        )
        return grpc.secure_channel(target, credentials, options=options)


def _validate_injected_context(context: Descriptor) -> None:
    """Check only fields written by the platform, not the whole protocol.

    Extra fields, messages, methods and JSON-name metadata are irrelevant.
    Field numbers/types and environment values must retain their wire meaning.
    """
    authority = cap.ExecutionContext.DESCRIPTOR
    for name in ("user_id", "environment", "request_id", "client"):
        field = context.fields_by_name.get(name)
        expected = authority.fields_by_name[name]
        if (
            field is None
            or field.number != expected.number
            or field.type != expected.type
            or field.is_repeated
            or (field.containing_oneof is not None and len(field.containing_oneof.fields) > 1)
        ):
            raise TransportError("INCOMPATIBLE_EXECUTION_CONTEXT")
    environment = context.fields_by_name["environment"].enum_type
    expected_environment = authority.fields_by_name["environment"].enum_type
    assert expected_environment is not None
    for name in ("PRT", "ONLINE"):
        value = environment.values_by_name.get(name) if environment is not None else None
        if value is None or value.number != expected_environment.values_by_name[name].number:
            raise TransportError("INCOMPATIBLE_EXECUTION_CONTEXT")


def registered_method(plan: RpcPlan) -> MethodDescriptor:
    if len(plan.descriptor_set_base64) > 2_800_000:
        raise TransportError("DESCRIPTOR_TOO_LARGE")
    try:
        raw = base64.b64decode(plan.descriptor_set_base64, validate=True)
        bundle = descriptor_pb2.FileDescriptorSet.FromString(raw)
        pending = {file.name: file for file in bundle.file}
        if len(pending) != len(bundle.file):
            raise TransportError("DUPLICATE_DESCRIPTOR_FILE")
        pool = descriptor_pool.DescriptorPool()
        resolved: set[str] = set()
        while pending:
            ready = [name for name, file in pending.items() if set(file.dependency) <= resolved]
            if not ready:
                raise TransportError("DESCRIPTOR_DEPENDENCY_INVALID")
            for name in ready:
                pool.Add(pending.pop(name))
                resolved.add(name)
        service = pool.FindServiceByName(plan.service_name)
        method = service.methods_by_name[plan.method_name]
        field = method.input_type.fields_by_name[plan.context_field]
        if (
            method.client_streaming
            or method.server_streaming
            or field.is_repeated
            or field.message_type is None
            or field.message_type.full_name != "a2flow.capability.v1.ExecutionContext"
        ):
            raise TransportError("REGISTERED_UNARY_CONTEXT_REQUIRED")
        _validate_injected_context(field.message_type)
        return method
    except TransportError:
        raise
    except (ValueError, TypeError, KeyError, binascii.Error, DecodeError) as error:
        raise TransportError("INVALID_REGISTERED_DESCRIPTOR") from error


def local_schema(schema: JsonObject) -> Draft7Validator:
    def inspect(value: JsonValue) -> None:
        if isinstance(value, dict):
            if "$ref" in value:
                ref = value["$ref"]
                if not isinstance(ref, str) or not ref.startswith("#"):
                    raise TransportError("EXTERNAL_SCHEMA_REFERENCE_FORBIDDEN")
            if "$dynamicRef" in value or "$recursiveRef" in value:
                raise TransportError("UNSUPPORTED_SCHEMA_REFERENCE")
            if "$schema" in value and value["$schema"] not in (
                "http://json-schema.org/draft-07/schema#",
                "https://json-schema.org/draft-07/schema#",
            ):
                raise TransportError("DRAFT7_SCHEMA_REQUIRED")
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    inspect(schema)
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema)


class GrpcTransport:
    def __init__(self, targets: Mapping[tuple[str, str], Endpoint]) -> None:
        self._targets = dict(targets)

    def execute(self, plan: RpcPlan, business: JsonObject, context: TrustedContext) -> JsonValue:
        method = registered_method(plan)
        field = method.input_type.fields_by_name[plan.context_field]
        if field.name in business or field.json_name in business:
            raise TransportError("RESERVED_EXECUTION_CONTEXT", "REQUEST_MAPPING_INVALID")
        if not 0 < plan.timeout_ms <= 120_000 or not 0 < plan.max_response_bytes <= 5_242_880:
            raise TransportError("INVALID_RPC_LIMITS")
        validator = local_schema(plan.technical_output_schema)
        request: Message = message_factory.GetMessageClass(method.input_type)()
        # ParseDict preserves exact integers and rejects unknown business fields.
        payload: JsonObject = dict(business)
        payload[field.json_name] = {
            "user_id": str(context.user_id),
            "environment": context.environment,
            "request_id": context.request_id,
            "client": context.client,
        }
        try:
            json_format.ParseDict(payload, request, ignore_unknown_fields=False)
        except (ValueError, TypeError, json_format.ParseError) as error:
            raise TransportError("INVALID_PROTOBUF_ARGUMENTS", "REQUEST_MAPPING_INVALID") from error
        wire = request.SerializeToString()
        if len(wire) > 1024 * 1024:
            raise TransportError("RPC_REQUEST_TOO_LARGE")
        endpoint = self._targets.get((plan.target_key, context.environment))
        if endpoint is None:
            raise TransportError("EXACT_TARGET_ENVIRONMENT_REQUIRED")
        try:
            with endpoint.open(plan.max_response_bytes) as channel:
                call: grpc.UnaryUnaryMultiCallable[bytes, bytes] = channel.unary_unary(
                    f"/{plan.service_name}/{plan.method_name}"
                )
                response_wire = call(wire, timeout=plan.timeout_ms / 1000)
        except grpc.RpcError as error:
            code = (
                "TRANSPORT_TIMEOUT"
                if error.code() == grpc.StatusCode.DEADLINE_EXCEEDED
                else "TRANSPORT_ERROR"
            )
            raise TransportError("DOWNSTREAM_RPC_FAILED", code) from None
        response: Message = message_factory.GetMessageClass(method.output_type)()
        response.ParseFromString(response_wire)
        # Same ProtoJSON lowerCamelCase/default-field behavior as the Java transport.
        result = cast(
            JsonValue,
            json.loads(
                json_format.MessageToJson(
                    response,
                    always_print_fields_with_no_presence=True,
                )
            ),
        )
        if not validator.is_valid(result):
            raise TransportError("RESPONSE_SCHEMA_INVALID", "RESPONSE_SCHEMA_INVALID")
        return result
