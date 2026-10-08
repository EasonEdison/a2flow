"""Explicit Python capability host; published-store access is read-only."""

from __future__ import annotations

import ipaddress
import os
import signal
import sys
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import FrameType

import grpc
from a2flow.capability.v1.capability_pb2_grpc import add_CapabilityExecutionServicer_to_server

from .executor import CapabilityExecutor
from .models import Environment, JsonObject, JsonValue
from .releases import PostgresReleaseReader
from .rpc import CapabilityRpcService, parse_object
from .transport import Endpoint, GrpcTransport

# Bound active work separately from accepted requests. The extra slots wait in
# the executor rather than rejecting ordinary parallel Tool/Describe bursts.
RPC_WORKERS = 4
RPC_MAX_IN_FLIGHT = 16


def text(value: JsonValue) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("configuration string required")
    return value


def targets(config: JsonObject) -> dict[tuple[str, str], Endpoint]:
    result: dict[tuple[str, str], Endpoint] = {}
    for key, environments in config.items():
        if not isinstance(environments, dict):
            raise ValueError("target environment map required")
        for environment, fields in environments.items():
            Environment(environment)
            if not isinstance(fields, dict) or set(fields) - {
                "host",
                "port",
                "loopbackPlaintext",
                "trustCertFile",
                "clientCertFile",
                "clientKeyFile",
            }:
                raise ValueError("invalid endpoint configuration")
            port = fields.get("port")
            plaintext = fields.get("loopbackPlaintext", False)
            if type(port) is not int or type(plaintext) is not bool:
                raise ValueError("typed endpoint port and mode required")
            result[(key, environment)] = Endpoint(
                text(fields.get("host")),
                port,
                plaintext,
                Path(text(fields["trustCertFile"])) if fields.get("trustCertFile") else None,
                Path(text(fields["clientCertFile"])) if fields.get("clientCertFile") else None,
                Path(text(fields["clientKeyFile"])) if fields.get("clientKeyFile") else None,
            )
    if not result:
        raise ValueError("at least one downstream target is required")
    return result


def configure_listener(server: grpc.Server, values: Mapping[str, str]) -> int:
    bind = values["A2FLOW_CAPABILITY_BIND"]
    host, port = bind.rsplit(":", 1)
    address = ipaddress.ip_address(host.strip("[]"))
    if not 1 <= int(port) <= 65535:
        raise ValueError("invalid listener port")
    mode = values["A2FLOW_CAPABILITY_RPC_MODE"]
    if mode == "LOOPBACK_TEST":
        if not address.is_loopback:
            raise ValueError("plaintext listener must be loopback")
        return server.add_insecure_port(bind)
    if mode != "MTLS":
        raise ValueError("explicit MTLS or LOOPBACK_TEST required")
    credentials = grpc.ssl_server_credentials(
        [
            (
                Path(values["A2FLOW_CAPABILITY_KEY_FILE"]).read_bytes(),
                Path(values["A2FLOW_CAPABILITY_CERT_FILE"]).read_bytes(),
            )
        ],
        root_certificates=Path(values["A2FLOW_CAPABILITY_CLIENT_CA_FILE"]).read_bytes(),
        require_client_auth=True,
    )
    return server.add_secure_port(bind, credentials)


def run(values: Mapping[str, str]) -> None:
    reader = PostgresReleaseReader(
        Path(values["A2FLOW_CAPABILITY_DSN_FILE"]).read_text().strip(),
        database=values["A2FLOW_CAPABILITY_DATABASE"],
        environment=Environment(values["A2FLOW_CAPABILITY_ENVIRONMENT"]),
    )
    reader.check_ready()
    transport = GrpcTransport(
        targets(parse_object(Path(values["A2FLOW_CAPABILITY_TARGETS_FILE"]).read_bytes()))
    )
    with ThreadPoolExecutor(max_workers=RPC_WORKERS, thread_name_prefix="capability-rpc") as pool:
        server = grpc.server(
            pool,
            maximum_concurrent_rpcs=RPC_MAX_IN_FLIGHT,
            options=(
                ("grpc.max_receive_message_length", 2 * 1024 * 1024),
                ("grpc.max_send_message_length", 6 * 1024 * 1024),
                ("grpc.enable_retries", 0),
            ),
        )
        add_CapabilityExecutionServicer_to_server(
            CapabilityRpcService(reader, CapabilityExecutor(transport)), server
        )
        try:
            if configure_listener(server, values) == 0:
                raise RuntimeError("listener bind failed")
            server.start()

            def stop(_signal: int, _frame: FrameType | None) -> None:
                server.stop(3)

            signal.signal(signal.SIGTERM, stop)
            print("CAPABILITY_RPC_READY", flush=True)
            server.wait_for_termination()
        finally:
            server.stop(3).wait(timeout=5)


def main() -> int:
    try:
        run(os.environ)
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(f"CAPABILITY_STARTUP_FAILED:{type(error).__name__}", file=sys.stderr)
        return 1
    return 0
