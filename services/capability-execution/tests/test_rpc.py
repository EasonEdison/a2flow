from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import grpc
import pytest
from a2flow.capability.v1 import capability_pb2 as cap
from a2flow.capability.v1 import capability_pb2_grpc as wire

from a2flow_capability.executor import CapabilityExecutor
from a2flow_capability.host import configure_listener, targets
from a2flow_capability.models import Environment, TrustedContext
from a2flow_capability.releases import ReleasedCapability, ReleaseError, ReleaseStorageError
from a2flow_capability.rpc import CapabilityRpcService, parse_object
from a2flow_capability.transport import GrpcTransport


class Reader:
    failure: Exception | None = None

    def resolve(self, asset_key: str, context: TrustedContext) -> ReleasedCapability:
        if self.failure:
            raise self.failure
        return ReleasedCapability(asset_key, "b1", "d1", 1, context.environment, {})


@pytest.fixture
def service() -> Iterator[tuple[wire.CapabilityExecutionStub, Reader]]:
    reader = Reader()
    with ThreadPoolExecutor(max_workers=1) as pool:
        server = grpc.server(pool)
        wire.add_CapabilityExecutionServicer_to_server(
            CapabilityRpcService(reader, CapabilityExecutor(GrpcTransport({}))), server
        )
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        try:
            with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
                yield wire.CapabilityExecutionStub(channel), reader
        finally:
            server.stop(0).wait()


def owner() -> cap.ExecutionContext:
    return cap.ExecutionContext(
        user_id=(1 << 63) - 1, environment=cap.PRT, request_id="rpc-test", client="PC"
    )


def test_failure_classes_and_safe_messages(
    service: tuple[wire.CapabilityExecutionStub, Reader],
) -> None:
    rpc, reader = service
    for failure, code in (
        (ReleaseError("ASSET_NOT_FOUND"), grpc.StatusCode.FAILED_PRECONDITION),
        (ReleaseStorageError("private-connection-data"), grpc.StatusCode.UNAVAILABLE),
        (RuntimeError("private-connection-data"), grpc.StatusCode.INTERNAL),
        (None, grpc.StatusCode.FAILED_PRECONDITION),
    ):
        reader.failure = failure
        with pytest.raises(grpc.RpcError) as caught:
            rpc.Resolve(cap.ResolveRequest(asset_key="draft", context=owner()), timeout=3)
        assert caught.value.code() == code
        assert "private-connection-data" not in caught.value.details()


def test_untrusted_identity_and_invalid_json_are_rejected(
    service: tuple[wire.CapabilityExecutionStub, Reader],
) -> None:
    rpc, _ = service
    invalid = owner()
    invalid.ClearField("user_id")
    empty_request_id = owner()
    empty_request_id.request_id = ""
    for context in (invalid, empty_request_id):
        with pytest.raises(grpc.RpcError) as caught:
            rpc.Resolve(cap.ResolveRequest(asset_key="draft", context=context), timeout=3)
        assert caught.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b"[]", b"\xff"):
        with pytest.raises(grpc.RpcError) as caught:
            rpc.Execute(
                cap.ExecuteRequest(asset_key="draft", context=owner(), arguments_json=raw),
                timeout=3,
            )
        assert caught.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_host_rejects_unsafe_modes_and_endpoint_configuration() -> None:
    with ThreadPoolExecutor(max_workers=1) as pool:
        server = grpc.server(pool)
        for bind, mode in (("0.0.0.0:19272", "LOOPBACK_TEST"), ("127.0.0.1:19272", "PLAINTEXT")):
            with pytest.raises(ValueError):
                configure_listener(
                    server, {"A2FLOW_CAPABILITY_BIND": bind, "A2FLOW_CAPABILITY_RPC_MODE": mode}
                )
    for config in ({}, {"content": {"PRT": {"host": "127.0.0.1", "port": True}}}):
        with pytest.raises(ValueError):
            targets(parse_object(json.dumps(config)))


def test_resolution_checks_descriptor_before_returning_contract() -> None:
    # Real compiler fixture, intentionally invalid descriptor: Resolve must fail
    # before model exposure, not merely when the eventual Execute is attempted.
    from test_compiler import _payload

    class PublishedReader:
        def resolve(self, key: str, context: TrustedContext) -> ReleasedCapability:
            return replace(
                ReleasedCapability(key, "b1", "d1", 1, Environment.PRT, _payload()),
                environment=context.environment,
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        server = grpc.server(pool)
        wire.add_CapabilityExecutionServicer_to_server(
            CapabilityRpcService(PublishedReader(), CapabilityExecutor(GrpcTransport({}))), server
        )
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        try:
            with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
                with pytest.raises(grpc.RpcError) as caught:
                    wire.CapabilityExecutionStub(channel).Resolve(
                        cap.ResolveRequest(asset_key="draft", context=owner()), timeout=3
                    )
                assert caught.value.code() == grpc.StatusCode.FAILED_PRECONDITION
        finally:
            server.stop(0).wait()
