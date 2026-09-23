"""Explicitly configured content gRPC host; no implicit migrations or plaintext fallback."""

from __future__ import annotations

import argparse
import ipaddress
import os
import signal
import sys
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType

import grpc
from a2flow.content.v1.content_pb2_grpc import add_ContentServiceServicer_to_server

from .models import Environment
from .repository import PostgresContentRepository
from .rpc import ContentRpcService
from .service import ContentService


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    conninfo: str = field(repr=False)
    environment: Environment
    database: str

    @classmethod
    def load(cls, values: Mapping[str, str]) -> DatabaseConfig:
        config = cls(
            Path(values["A2FLOW_CONTENT_DSN_FILE"]).read_text().strip(),
            Environment(values["A2FLOW_CONTENT_ENVIRONMENT"]),
            values["A2FLOW_CONTENT_DATABASE"],
        )
        if not config.conninfo or not config.database:
            raise ValueError("database configuration is required")
        return config


def configure_listener(server: grpc.Server, values: Mapping[str, str]) -> int:
    target = values["A2FLOW_CONTENT_BIND"]
    host, raw_port = target.rsplit(":", 1)
    address = ipaddress.ip_address(host.strip("[]"))
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise ValueError("invalid port")
    mode = values["A2FLOW_CONTENT_RPC_MODE"]
    if mode == "LOOPBACK_TEST":
        if not address.is_loopback:
            raise ValueError("test plaintext must bind a loopback IP")
        return server.add_insecure_port(target)
    if mode != "MTLS":
        raise ValueError("explicit MTLS or LOOPBACK_TEST mode required")
    credentials = grpc.ssl_server_credentials(
        [
            (
                Path(values["A2FLOW_CONTENT_KEY_FILE"]).read_bytes(),
                Path(values["A2FLOW_CONTENT_CERT_FILE"]).read_bytes(),
            ),
        ],
        root_certificates=Path(values["A2FLOW_CONTENT_CLIENT_CA_FILE"]).read_bytes(),
        require_client_auth=True,
    )
    return server.add_secure_port(target, credentials)


def run(values: Mapping[str, str], *, migrate_only: bool = False) -> None:
    config = DatabaseConfig.load(values)
    repository = PostgresContentRepository(
        config.conninfo, environment=config.environment, database=config.database
    )
    if migrate_only:
        repository.setup()
        print("CONTENT_SCHEMA_READY")
        return
    # Serving never implicitly creates or alters database objects.
    repository.check_ready()
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="content-rpc") as executor:
        server = grpc.server(
            executor,
            maximum_concurrent_rpcs=4,
            options=(
                ("grpc.max_receive_message_length", 1024 * 1024),
                ("grpc.max_send_message_length", 5 * 1024 * 1024),
                ("grpc.enable_retries", 0),
            ),
        )
        add_ContentServiceServicer_to_server(ContentRpcService(ContentService(repository)), server)
        try:
            if configure_listener(server, values) == 0:
                raise RuntimeError("could not bind content listener")
            server.start()

            def stop(_signum: int, _frame: FrameType | None) -> None:
                server.stop(grace=3)

            signal.signal(signal.SIGTERM, stop)
            print("CONTENT_RPC_READY", flush=True)
            server.wait_for_termination()
        finally:
            server.stop(grace=3).wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrate-only", action="store_true")
    args = parser.parse_args()
    try:
        run(os.environ, migrate_only=args.migrate_only)
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        # Connection exceptions may contain credentials; never print their messages.
        print(f"CONTENT_STARTUP_FAILED:{type(error).__name__}", file=sys.stderr)
        return 1
    return 0
