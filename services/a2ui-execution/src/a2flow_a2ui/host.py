"""Joint CapabilityExecution and A2uiExecution gRPC host."""

from __future__ import annotations

import os
import signal
import sys
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import FrameType

import grpc
from a2flow.a2ui.v1.a2ui_pb2_grpc import add_A2uiExecutionServicer_to_server
from a2flow.capability.v1.capability_pb2_grpc import add_CapabilityExecutionServicer_to_server
from a2flow_capability.executor import CapabilityExecutor
from a2flow_capability.host import configure_listener, targets
from a2flow_capability.invoker import PostgresCapabilityIndex, PublishedCapabilityInvoker
from a2flow_capability.models import Environment
from a2flow_capability.releases import PostgresReleaseReader
from a2flow_capability.rpc import CapabilityRpcService, parse_object
from a2flow_capability.transport import GrpcTransport

from .releases import PostgresApplicationReader
from .rpc import A2uiRpcService
from .runtime import A2uiRuntimeService


def _secret(path: str) -> str:
    value = Path(path).read_text().strip()
    if not value:
        raise ValueError("database credential file is empty")
    return value


def run(values: Mapping[str, str]) -> None:
    environment = Environment(values["A2FLOW_CAPABILITY_ENVIRONMENT"])
    management_dsn = _secret(values["A2FLOW_CAPABILITY_DSN_FILE"])
    management_database = values["A2FLOW_CAPABILITY_DATABASE"]
    capability_reader = PostgresReleaseReader(management_dsn, management_database, environment)
    application_reader = PostgresApplicationReader(management_dsn, management_database, environment)
    capability_reader.check_ready()
    application_reader.check_ready()
    transport = GrpcTransport(
        targets(parse_object(Path(values["A2FLOW_CAPABILITY_TARGETS_FILE"]).read_bytes()))
    )
    executor = CapabilityExecutor(transport)
    index = PostgresCapabilityIndex(
        _secret(values["A2FLOW_RUNTIME_ASSET_DSN_FILE"]),
        values["A2FLOW_RUNTIME_ASSET_DATABASE"],
        environment,
        values["A2FLOW_RUNTIME_ASSET_NAMESPACE"],
    )
    invoker = PublishedCapabilityInvoker(capability_reader, executor, index)
    runtime = A2uiRuntimeService(application_reader, invoker)
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="a2flow-engine-rpc") as pool:
        server = grpc.server(
            pool,
            maximum_concurrent_rpcs=4,
            options=(
                ("grpc.max_receive_message_length", 2 * 1024 * 1024),
                ("grpc.max_send_message_length", 6 * 1024 * 1024),
                ("grpc.enable_retries", 0),
            ),
        )
        add_CapabilityExecutionServicer_to_server(
            CapabilityRpcService(capability_reader, executor), server
        )
        add_A2uiExecutionServicer_to_server(A2uiRpcService(runtime), server)
        try:
            if configure_listener(server, values) == 0:
                raise RuntimeError("listener bind failed")
            server.start()

            def stop(_signal: int, _frame: FrameType | None) -> None:
                server.stop(3)

            signal.signal(signal.SIGTERM, stop)
            print("A2FLOW_ENGINE_RPC_READY", flush=True)
            server.wait_for_termination()
        finally:
            server.stop(3).wait(timeout=5)


def main() -> int:
    try:
        run(os.environ)
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(f"A2FLOW_ENGINE_STARTUP_FAILED:{type(error).__name__}", file=sys.stderr)
        return 1
    return 0
