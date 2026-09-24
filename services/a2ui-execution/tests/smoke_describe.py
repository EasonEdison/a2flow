"""Read-only mTLS smoke probe for authoritative published A2UI applications.

This script calls Describe only. It never publishes, activates an application,
executes a capability, or writes a database.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NoReturn, cast

import grpc
from a2flow.a2ui.v1 import a2ui_pb2 as ui
from a2flow.a2ui.v1 import a2ui_pb2_grpc as ui_rpc
from a2flow.capability.v1 import capability_pb2 as cap

DEFAULT_APPS = (
    "reading-point-selector",
    "content-topic-selector",
    "content-manuscript-editor",
)
MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1
SERVER_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")


class ProbeFailure(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DescriptionEvidence:
    app_code: str
    source_id: str
    digest: str
    app_build_id: str
    interaction_mode: str
    protocol_version: str
    catalog_id: str
    catalog_revision: str
    catalog_digest: str
    actions: tuple[str, ...]


def _duplicate_free_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProbeFailure("DESCRIBE_SCHEMA_INVALID")
        result[key] = value
    return result


def _reject_constant(_value: str) -> NoReturn:
    raise ProbeFailure("DESCRIBE_SCHEMA_INVALID")


def _schema(raw: bytes) -> dict[str, object]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_duplicate_free_object,
            parse_constant=_reject_constant,
        )
    except ProbeFailure:
        raise
    except (UnicodeError, ValueError, RecursionError):
        raise ProbeFailure("DESCRIBE_SCHEMA_INVALID") from None
    if not isinstance(value, dict):
        raise ProbeFailure("DESCRIBE_SCHEMA_INVALID")
    return cast(dict[str, object], value)


def validate(app_code: str, response: ui.DescribeResponse) -> DescriptionEvidence:
    release = response.release
    catalog = response.catalog
    if response.error_code:
        raise ProbeFailure(response.error_code)
    if (
        release.app_code != app_code
        or release.environment != cap.PRT
        or not release.source_id
        or not release.digest
        or not release.app_build_id
    ):
        raise ProbeFailure("DESCRIBE_RELEASE_INVALID")
    if response.interaction_mode not in {"DISPLAY_ONLY", "INTERACTIVE"}:
        raise ProbeFailure("DESCRIBE_MODE_INVALID")
    if (
        catalog.protocol_version != "v0.9.1"
        or not catalog.catalog_id
        or not catalog.catalog_revision
        or not catalog.catalog_digest
    ):
        raise ProbeFailure("DESCRIBE_CATALOG_INVALID")
    _schema(response.params_schema_json)
    actions: list[str] = []
    identities: set[tuple[str, str, str]] = set()
    for action in response.actions:
        identity = (action.surface_id, action.component_id, action.action_name)
        if not all(identity) or identity in identities:
            raise ProbeFailure("DESCRIBE_ACTION_INVALID")
        identities.add(identity)
        _schema(action.context_schema_json)
        actions.append(action.action_name)
    return DescriptionEvidence(
        app_code,
        release.source_id,
        release.digest,
        release.app_build_id,
        response.interaction_mode,
        catalog.protocol_version,
        catalog.catalog_id,
        catalog.catalog_revision,
        catalog.catalog_digest,
        tuple(actions),
    )


def _read_nonempty(path: Path) -> bytes:
    try:
        value = path.read_bytes()
    except OSError:
        raise ProbeFailure("MTLS_FILE_INVALID") from None
    if not value:
        raise ProbeFailure("MTLS_FILE_INVALID")
    return value


def run(arguments: argparse.Namespace) -> tuple[DescriptionEvidence, ...]:
    if (
        arguments.target != "127.0.0.1:8794"
        or type(arguments.user_id) is not int
        or not MIN_I64 <= arguments.user_id <= MAX_I64
        or arguments.client not in {"PC", "APP"}
        or not math.isfinite(arguments.timeout)
        or arguments.timeout <= 0
        or not arguments.apps
        or len(arguments.apps) != len(set(arguments.apps))
    ):
        raise ProbeFailure("PROBE_ARGUMENT_INVALID")
    if any(not value or len(value) > 256 for value in arguments.apps):
        raise ProbeFailure("PROBE_ARGUMENT_INVALID")
    options: list[tuple[str, str | int]] = [
        ("grpc.enable_retries", 0),
        ("grpc.max_receive_message_length", 2 * 1024 * 1024),
    ]
    if arguments.server_name is not None:
        if not SERVER_NAME.fullmatch(arguments.server_name):
            raise ProbeFailure("PROBE_ARGUMENT_INVALID")
        options.extend(
            (
                ("grpc.ssl_target_name_override", arguments.server_name),
                ("grpc.default_authority", arguments.server_name),
            )
        )
    credentials = grpc.ssl_channel_credentials(
        root_certificates=_read_nonempty(arguments.ca_file),
        private_key=_read_nonempty(arguments.key_file),
        certificate_chain=_read_nonempty(arguments.cert_file),
    )
    channel = grpc.secure_channel(arguments.target, credentials, options=tuple(options))
    stub = ui_rpc.A2uiExecutionStub(channel)
    evidence: list[DescriptionEvidence] = []
    try:
        grpc.channel_ready_future(channel).result(timeout=arguments.timeout)
        for app_code in arguments.apps:
            context = cap.ExecutionContext(
                user_id=arguments.user_id,
                environment=cap.PRT,
                request_id=f"describe-smoke:{uuid.uuid4()}",
                client=arguments.client,
            )
            response = stub.Describe(
                ui.DescribeRequest(context=context, app_code=app_code),
                timeout=arguments.timeout,
                wait_for_ready=False,
            )
            evidence.append(validate(app_code, response))
    except grpc.FutureTimeoutError:
        raise ProbeFailure("RPC_CHANNEL_NOT_READY") from None
    except grpc.RpcError as error:
        detail = error.details() or ""
        if (
            error.code() is grpc.StatusCode.FAILED_PRECONDITION
            and detail.isascii()
            and 0 < len(detail) <= 120
            and all(
                character.isupper() or character.isdigit() or character == "_"
                for character in detail
            )
        ):
            raise ProbeFailure(detail) from None
        if error.code() in {grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED}:
            raise ProbeFailure("RPC_AUTHENTICATION_FAILED") from None
        if error.code() is grpc.StatusCode.DEADLINE_EXCEEDED:
            raise ProbeFailure("RPC_TIMEOUT") from None
        raise ProbeFailure("RPC_DESCRIBE_FAILED") from None
    finally:
        channel.close()
    return tuple(evidence)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--target", default="127.0.0.1:8794")
    value.add_argument("--ca-file", required=True, type=Path)
    value.add_argument("--cert-file", required=True, type=Path)
    value.add_argument("--key-file", required=True, type=Path)
    value.add_argument("--server-name")
    value.add_argument("--user-id", required=True, type=int)
    value.add_argument("--client", choices=("PC", "APP"), default="PC")
    value.add_argument("--timeout", type=float, default=10.0)
    value.add_argument("--app", dest="apps", action="append", default=None)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.apps is None:
        arguments.apps = list(DEFAULT_APPS)
    try:
        evidence = run(arguments)
    except ProbeFailure as error:
        print(f"A2UI_DESCRIBE_SMOKE_FAILED:{error}", file=sys.stderr)
        return 1
    for item in evidence:
        print(json.dumps(asdict(item), ensure_ascii=False, separators=(",", ":")))
    print(f"A2UI_DESCRIBE_SMOKE_PASS count={len(evidence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
