"""Grant-bound gRPC tool client. No retries, browser cookies or identity selectors."""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import grpc
from a2flow.management.v1 import management_agent_pb2 as pb
from a2flow.management.v1 import management_agent_pb2_grpc as rpc
from jsonschema import Draft202012Validator

from .models import AgentError, AgentIdentity, decode, encode, identifier


@dataclass(frozen=True)
class ToolDescription:
    name: str
    description: str
    schema: dict[str, Any]
    mutating: bool

    def validate(self, value: object) -> object:
        try:
            Draft202012Validator(self.schema).validate(value)
        except Exception:
            raise ValueError("MANAGEMENT_TOOL_ARGUMENT_INVALID") from None
        return value


def local_target(target: str) -> str:
    try:
        host, port = target.rsplit(":", 1)
        if not ipaddress.ip_address(host.strip("[]")).is_loopback or not 1 <= int(port) <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("LOOPBACK_GRPC_TARGET_REQUIRED") from None
    return target


class ManagementToolBridge:
    def __init__(self, channel: grpc.Channel) -> None:
        self.channel = channel
        self.stub = rpc.ManagementToolsStub(self.channel)

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> ManagementToolBridge:
        # Same trusted deployment configuration as RpcClient; no downgrade or implicit plaintext.
        target = local_target(environment.get("A2FLOW_ENGINE_RPC_TARGET", ""))
        mode = environment.get("A2FLOW_ENGINE_RPC_MODE", "")
        options = (("grpc.enable_retries", 0), ("grpc.max_receive_message_length", 2 * 1024 * 1024))
        if mode == "LOOPBACK":
            return cls(grpc.insecure_channel(target, options=options))
        if mode != "MTLS":
            raise AgentError("RPC_CONFIG_REQUIRED")
        paths = [
            environment.get("A2FLOW_ENGINE_RPC_" + key + "_FILE", "")
            for key in ("CA", "CERT", "KEY")
        ]
        if not all(paths):
            raise AgentError("RPC_MTLS_REQUIRED")
        try:
            ca, cert, key = (Path(path).read_bytes() for path in paths)
        except OSError:
            raise AgentError("RPC_MTLS_UNAVAILABLE") from None
        credentials = grpc.ssl_channel_credentials(ca, key, cert)
        return cls(grpc.secure_channel(target, credentials, options=options))

    def describe(self, who: AgentIdentity) -> list[ToolDescription]:
        try:
            response = self.stub.DescribeTools(pb.DescribeToolsRequest(grant=who.grant), timeout=15)
        except grpc.RpcError:
            raise AgentError("MANAGEMENT_TOOLS_UNAVAILABLE") from None
        if response.error_code:
            raise AgentError(response.error_code)
        if not 1 <= len(response.tools) <= 100:
            raise AgentError("INVALID_MANAGEMENT_TOOL_CATALOG")
        result = []
        for tool in response.tools:
            identifier(tool.name)
            schema = decode(tool.input_schema_json)
            if (
                not isinstance(schema, dict)
                or schema.get("type") != "object"
                or schema.get("additionalProperties") is not False
            ):
                raise AgentError("MANAGEMENT_TOOL_SCHEMA_NOT_CLOSED")
            Draft202012Validator.check_schema(schema)
            result.append(ToolDescription(tool.name, tool.description, schema, tool.mutating))
        if len({x.name for x in result}) != len(result):
            raise AgentError("DUPLICATE_MANAGEMENT_TOOL")
        return result

    def execute(
        self,
        who: AgentIdentity,
        cid: str,
        turn: dict[str, Any],
        call_id: str,
        request_id: str,
        name: str,
        arguments: dict[str, Any],
        deadline: float,
    ) -> dict[str, Any]:
        timeout = min(60.0, deadline - time.monotonic())
        if timeout <= 0:
            raise AgentError("MANAGEMENT_TURN_DEADLINE")
        try:
            response = self.stub.ExecuteTool(
                pb.ExecuteToolRequest(
                    grant=who.grant,
                    conversation_id=cid,
                    turn_id=turn["turn_id"],
                    tool_call_id=call_id,
                    request_id=request_id,
                    name=name,
                    arguments_json=encode(arguments),
                ),
                timeout=timeout,
            )
            return self.result(response, request_id)
        except grpc.RpcError:
            return dict(
                status="UNKNOWN",
                errorCode="MANAGEMENT_TRANSPORT_UNCONFIRMED",
                result=None,
                requestId=request_id,
            )

    def read_receipt(
        self, who: AgentIdentity, cid: str, request_id: str, deadline: float
    ) -> dict[str, Any]:
        timeout = min(15.0, deadline - time.monotonic())
        if timeout <= 0:
            raise AgentError("MANAGEMENT_TURN_DEADLINE")
        try:
            response = self.stub.ReadReceipt(
                pb.ReadReceiptRequest(grant=who.grant, conversation_id=cid, request_id=request_id),
                timeout=timeout,
            )
            return self.result(response, request_id)
        except grpc.RpcError:
            return dict(
                status="UNKNOWN",
                errorCode="MANAGEMENT_RECEIPT_UNAVAILABLE",
                result=None,
                requestId=request_id,
            )

    @staticmethod
    def result(response: pb.ToolResult, request_id: str) -> dict[str, Any]:
        if response.request_id != request_id or response.status not in {
            "SUCCEEDED",
            "REJECTED",
            "UNKNOWN",
            "RUNNING",
            "NOT_FOUND",
        }:
            raise AgentError("INVALID_MANAGEMENT_RECEIPT")
        payload = decode(response.result_json) if response.result_json else None
        if payload is not None and not isinstance(payload, dict):
            raise AgentError("INVALID_MANAGEMENT_RESULT")
        return dict(
            status=response.status,
            errorCode=response.error_code,
            result=payload,
            requestId=request_id,
        )
