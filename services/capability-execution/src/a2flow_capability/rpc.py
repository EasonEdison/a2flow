"""Published-only CapabilityExecution RPC boundary with source identity checks."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Protocol, TypeVar, cast

import grpc
from a2flow.capability.v1 import capability_pb2 as pb
from a2flow.capability.v1 import capability_pb2_grpc as rpc

from .compiler import CapabilityCompileError, CompiledCapability, compile_capability
from .executor import CapabilityExecutor
from .models import (
    CapabilityExecutionError,
    CapabilityTransportError,
    Environment,
    JsonObject,
    JsonValue,
    TrustedContext,
)
from .releases import ReleasedCapability, ReleaseError, ReleaseStorageError
from .transport import registered_method

T = TypeVar("T")


class RequestCancelled(Exception):
    pass


class ReleaseReader(Protocol):
    def resolve(self, asset_key: str, context: TrustedContext) -> ReleasedCapability: ...


def json_value(value: object) -> JsonValue:
    if value is None or type(value) in (str, int, bool):
        return cast(JsonValue, value)
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            raise ValueError("JSON object keys must be strings")
        return {key: json_value(item) for key, item in value.items()}
    raise ValueError("invalid JSON value")


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON property")
        result[key] = value
    return result


def parse_object(raw: bytes | str) -> JsonObject:
    value = json_value(json.loads(raw, object_pairs_hook=unique_object))
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def trusted(value: pb.ExecutionContext) -> TrustedContext:
    if not value.HasField("user_id") or value.client not in ("PC", "APP"):
        raise ValueError("trusted runtime context required")
    return TrustedContext(
        value.user_id,
        Environment(pb.Environment.Name(value.environment)),
        value.request_id,
        value.client,
    )


def invoke(context: grpc.ServicerContext, operation: Callable[[], T]) -> T:
    if not context.is_active():
        context.abort(grpc.StatusCode.CANCELLED, "REQUEST_CANCELLED")
    try:
        return operation()
    except RequestCancelled:
        context.abort(grpc.StatusCode.CANCELLED, "REQUEST_CANCELLED")
    except (CapabilityCompileError, CapabilityTransportError):
        context.abort(grpc.StatusCode.FAILED_PRECONDITION, "PUBLISHED_CAPABILITY_CONTRACT_INVALID")
    except CapabilityExecutionError as error:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, error.code.value)
    except ReleaseStorageError:
        context.abort(grpc.StatusCode.UNAVAILABLE, "CAPABILITY_RELEASE_STORAGE_UNAVAILABLE")
    except ReleaseError as error:
        context.abort(grpc.StatusCode.FAILED_PRECONDITION, error.code)
    except (ValueError, UnicodeError):
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "INVALID_CAPABILITY_REQUEST_OR_CONTRACT")
    except Exception:
        context.abort(grpc.StatusCode.INTERNAL, "CAPABILITY_EXECUTION_FAILED")


class CapabilityRpcService(rpc.CapabilityExecutionServicer):
    def __init__(self, reader: ReleaseReader, executor: CapabilityExecutor) -> None:
        self._reader = reader
        self._executor = executor

    def _compile(self, key: str, owner: TrustedContext) -> CompiledCapability:
        if not key or len(key) > 256:
            raise ValueError("invalid asset key")
        release = self._reader.resolve(key, owner)
        if release.asset_key != key or release.environment != owner.environment:
            raise ReleaseError("CAPABILITY_RELEASE_IDENTITY_INVALID")
        compiled = compile_capability(
            release.payload,
            release.source_id,
            release.source_digest,
            release.environment,
            release.version,
            owner.client,
        )
        registered_method(compiled.plan)
        return compiled

    def Resolve(
        self, request: pb.ResolveRequest, context: grpc.ServicerContext
    ) -> pb.ResolveResponse:
        def operation() -> pb.ResolveResponse:
            compiled = self._compile(request.asset_key, trusted(request.context))
            plan = compiled.plan
            return pb.ResolveResponse(
                asset_key=request.asset_key,
                action_code=plan.action_code,
                capability_version=plan.capability_version,
                description=compiled.description,
                input_schema_json=json.dumps(compiled.input_schema, allow_nan=False),
                key_output_fields_json=json.dumps(compiled.key_output_fields, allow_nan=False),
                resolved_environment=pb.Environment.Value(plan.resolved_environment.value),
                source_id=plan.source_id,
                source_digest=plan.source_digest,
            )

        return invoke(context, operation)

    def Execute(
        self, request: pb.ExecuteRequest, context: grpc.ServicerContext
    ) -> pb.ExecuteResponse:
        def operation() -> pb.ExecuteResponse:
            owner = trusted(request.context)
            if len(request.arguments_json) > 1024 * 1024:
                raise ValueError("arguments exceed limit")
            arguments = parse_object(request.arguments_json.decode("utf-8"))
            compiled = self._compile(request.asset_key, owner)
            plan = compiled.plan
            if (
                not request.expected_source_id
                or not request.expected_source_digest
                or request.expected_source_id != plan.source_id
                or request.expected_source_digest != plan.source_digest
            ):
                raise ReleaseError("SOURCE_VERSION_CHANGED")
            if not context.is_active():
                raise RequestCancelled
            result = self._executor.execute(plan, arguments, owner)
            return pb.ExecuteResponse(
                success=result.success,
                action_code=result.action_code,
                capability_version=result.capability_version,
                resolved_environment=pb.Environment.Value(result.resolved_environment.value),
                data_json=json.dumps(result.data, ensure_ascii=False, allow_nan=False).encode(),
                error_code=result.error_code.value if result.error_code else "",
                message=result.message or "",
                request_id=owner.request_id,
                source_id=plan.source_id,
                source_digest=plan.source_digest,
            )

        return invoke(context, operation)
