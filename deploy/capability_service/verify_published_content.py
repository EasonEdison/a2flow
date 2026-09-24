"""Isolated PG -> published M snapshot -> two real Python gRPC hosts probe.

Requires an empty disposable management database and an initialized disposable
content database. Never points at production. Fixtures are synthetic M records,
not evidence of browser authoring or production publication.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

import grpc
import psycopg
from a2flow.capability.v1 import capability_pb2 as cap
from a2flow.capability.v1.capability_pb2_grpc import CapabilityExecutionStub
from a2flow.content.v1 import content_pb2 as content
from a2flow.content.v1.content_pb2_grpc import ContentServiceStub
from a2flow_capability.models import Environment, TrustedContext
from a2flow_capability.releases import PostgresReleaseReader
from google.protobuf import descriptor_pb2


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload() -> dict[str, object]:
    descriptors = descriptor_pb2.FileDescriptorSet()
    cap.DESCRIPTOR.CopyToProto(descriptors.file.add())
    content.DESCRIPTOR.CopyToProto(descriptors.file.add())
    fields = [
        {"toolField": name, "type": "string", "source": "MODEL_INPUT", "required": True}
        for name in ("title", "audience", "outputFormat")
    ]
    variant = {
        "apiSource": {"sourceType": "GRPC"},
        "modelContract": {"description": "创建阅读创作项目", "inputFields": fields},
        "executionBinding": {
            "bindingType": "GRPC",
            "target": {
                "targetKey": "content",
                "serviceName": "a2flow.content.v1.ContentService",
                "methodName": "CreateProject",
                "contextField": "context",
                "descriptorSetBase64": base64.b64encode(descriptors.SerializeToString()).decode(),
            },
            "requestMappingsJson": encode(
                {name: name for name in ("title", "audience", "outputFormat")}
            ),
            "contextMappingsJson": "{}",
            "timeoutMs": 3000,
            "maxResponseBytes": 1048576,
            "idempotency": "NONE",
            "responsePolicy": "ORIGINAL",
        },
        "resultContract": {
            "keyOutputFields": [{"path": "id", "description": "项目标识"}],
            "technicalOutputSchema": encode({"type": "object", "required": ["id", "title"]}),
        },
    }
    return {
        "draftId": "content-project-create",
        "revision": 1,
        "status": "EDITING",
        "draft": {
            "basicInfo": {"actionCode": "content.project.create"},
            "governance": {"enabled": True, "emergencyDisabled": False},
            "supportedClients": ["COMMON"],
            "clientVariants": {"COMMON": variant},
        },
    }


def pointer(environment: str, number: int) -> dict[str, object]:
    source = "build" if environment == "PRT" else "version"
    return {
        "environment": environment,
        "sourceType": source.upper(),
        "sourceId": f"{source}-{number}",
        "version": number,
        "digest": f"synthetic-digest-{number}",
    }


def seed(dsn: str, *, prt_version: int | None = 1, gray: bool = False) -> None:
    key = "content-project-create"
    builds: list[dict[str, object]] = []
    versions: list[dict[str, object]] = []
    with psycopg.connect(dsn) as connection:
        for number in (1, 2):
            digest = f"synthetic-digest-{number}"
            snapshot = {
                "assetType": "CAPABILITY_ACTION",
                "assetKey": key,
                "digest": digest,
                "payloadJson": encode(payload()),
            }
            build = {
                "buildId": f"build-{number}",
                "status": "SUCCEEDED",
                "targetVersion": number,
                "sourceDigest": digest,
                "snapshot": snapshot,
            }
            version = {
                "versionId": f"version-{number}",
                "version": number,
                "sourceBuildId": f"build-{number}",
                "snapshotBuildId": f"build-{number}",
                "inputDigest": digest,
                "sourceDigest": digest,
            }
            for collection, record, identifier, destination in (
                ("builds", build, f"build-{number}", builds),
                ("versions", version, f"version-{number}", versions),
            ):
                raw = encode(
                    {
                        "assetType": "CAPABILITY_ACTION",
                        "assetKey": key,
                        "collection": collection,
                        "recordId": identifier,
                        "payload": record,
                    }
                )
                reference = hashlib.sha256(raw.encode()).hexdigest()
                connection.execute(
                    "INSERT INTO skill_asset_release_state"
                    "(asset_type,asset_key,revision,state_json,deleted) VALUES (%s,%s,1,%s,0)"
                    " ON CONFLICT(asset_type,asset_key)"
                    " DO UPDATE SET state_json=excluded.state_json",
                    ("RELEASE_RECORD", reference, encode({"recordJson": raw})),
                )
                destination.append({"recordRef": reference})
        online = pointer("ONLINE", 1)
        if gray:
            online.update(
                {
                    "candidate": pointer("ONLINE", 2),
                    "grayStatus": "GRAYING",
                    "grayRule": {"percentage": 1, "userIdWhitelist": [str((1 << 63) - 1)]},
                }
            )
        environments: dict[str, object] = {"ONLINE": online}
        if prt_version is not None:
            environments["PRT"] = pointer("PRT", prt_version)
        state = {
            "assetType": "CAPABILITY_ACTION",
            "assetKey": key,
            "revision": 1,
            "recordStorageVersion": 1,
            "builds": builds,
            "versions": versions,
            "environments": environments,
            "deployments": [],
            "validations": {},
        }
        connection.execute(
            "INSERT INTO skill_asset_release_state"
            "(asset_type,asset_key,revision,state_json,deleted) VALUES (%s,%s,1,%s,0)"
            " ON CONFLICT(asset_type,asset_key) DO UPDATE SET state_json=excluded.state_json",
            ("CAPABILITY_ACTION", key, encode(state)),
        )


def main() -> None:
    if os.environ.get("A2FLOW_VERIFY_ISOLATED") != "1":
        raise ValueError("explicit isolated write-test opt-in required")
    dsn = Path(os.environ["A2FLOW_CAPABILITY_DSN_FILE"]).read_text().strip()
    database = os.environ["A2FLOW_CAPABILITY_DATABASE"]
    if not database.endswith("_test"):
        raise ValueError("disposable _test database required")
    if len(sys.argv) == 1:
        for name in ("VERIFY_CAPABILITY_ADDRESS", "VERIFY_CONTENT_ADDRESS"):
            address, port = os.environ[name].rsplit(":", 1)
            if address != "127.0.0.1" or not 1 <= int(port) <= 65535:
                raise ValueError("probe only accepts literal loopback RPC hosts")
    if len(sys.argv) > 1 and sys.argv[1] == "--seed":
        with psycopg.connect(dsn) as connection:
            assert connection.execute("SELECT current_database()").fetchone() == (database,)
            connection.execute(
                "CREATE TABLE skill_asset_release_state ("
                "asset_type TEXT,asset_key TEXT,revision INTEGER,state_json TEXT,"
                "deleted INTEGER NOT NULL DEFAULT 0,UNIQUE(asset_type,asset_key))"
            )
        seed(dsn)
        print("SYNTHETIC_M_RELEASE_SEEDED")
        return
    seed(dsn)
    user_id = (1 << 63) - 1
    context = cap.ExecutionContext(
        user_id=user_id, environment=cap.PRT, request_id="published-content-create", client="PC"
    )
    with (
        grpc.insecure_channel(os.environ["VERIFY_CAPABILITY_ADDRESS"]) as channel,
        grpc.insecure_channel(os.environ["VERIFY_CONTENT_ADDRESS"]) as content_channel,
    ):
        grpc.channel_ready_future(channel).result(timeout=10)
        rpc = CapabilityExecutionStub(channel)
        downstream = ContentServiceStub(content_channel)
        resolved = rpc.Resolve(
            cap.ResolveRequest(asset_key="content-project-create", context=context), timeout=5
        )
        assert resolved.source_id == "build-1"
        request = cap.ExecuteRequest(
            asset_key="content-project-create",
            context=context,
            expected_source_id=resolved.source_id,
            expected_source_digest=resolved.source_digest,
            arguments_json=encode(
                {"title": "阅读到创作联调", "audience": "读者", "outputFormat": "ARTICLE"}
            ).encode(),
        )
        result = rpc.Execute(request, timeout=5)
        assert result.success, (result.error_code, result.message)
        project = json.loads(result.data_json)
        found = downstream.GetProject(
            content.GetProjectRequest(context=context, project_id=project["id"]), timeout=5
        )
        assert found.title == "阅读到创作联调"
        assert rpc.Execute(request, timeout=5).data_json == result.data_json
        print("PASS published split records -> compiler -> capability RPC -> content RPC -> PG")
        print("PASS signed64 identity and downstream requestId replay")
        other = cap.ExecutionContext(
            user_id=user_id - 1, environment=cap.PRT, request_id="other-user", client="PC"
        )
        try:
            downstream.GetProject(
                content.GetProjectRequest(context=other, project_id=project["id"]), timeout=5
            )
        except grpc.RpcError as error:
            assert error.code() == grpc.StatusCode.NOT_FOUND
        else:
            raise AssertionError("cross-user read succeeded")
        print("PASS cross-user content isolation")
        seed(dsn, prt_version=2)
        request.context.request_id = "stale-new-request"
        try:
            rpc.Execute(request, timeout=5)
        except grpc.RpcError as error:
            assert error.code() == grpc.StatusCode.FAILED_PRECONDITION
            assert error.details() == "SOURCE_VERSION_CHANGED"
        else:
            raise AssertionError("stale source executed")
        print("PASS publication switch rejects old source pins")
        assert (
            downstream.ListProjects(
                content.ListProjectsRequest(context=context, page=1, page_size=10), timeout=5
            ).total
            == 1
        )
        seed(dsn, prt_version=None)
        try:
            rpc.Resolve(cap.ResolveRequest(asset_key=request.asset_key, context=context), timeout=5)
        except grpc.RpcError as error:
            assert error.code() == grpc.StatusCode.FAILED_PRECONDITION
        else:
            raise AssertionError("PRT fell back to ONLINE")
        online = PostgresReleaseReader(dsn, database, Environment.ONLINE)
        release = online.resolve(
            request.asset_key,
            TrustedContext(user_id, Environment.ONLINE, "online-selection", "APP"),
        )
        assert release.source_id == "version-1"
        print("PASS no cross-environment fallback; ONLINE compact version resolution")
        seed(dsn, gray=True)
        for identity, expected in ((user_id, 2), (0, 2), (-1, 1), (-(1 << 63), 1)):
            selected = online.resolve(
                request.asset_key,
                TrustedContext(identity, Environment.ONLINE, "gray-selection", "PC"),
            )
            assert selected.version == expected
        print("PASS ONLINE stable/gray percentage and signed64 whitelist")
        with psycopg.connect(dsn) as connection:
            connection.execute(
                "UPDATE skill_asset_release_state SET state_json=%s "
                "WHERE asset_type='RELEASE_RECORD'",
                (encode({"recordJson": "{}"}),),
            )
        try:
            rpc.Resolve(cap.ResolveRequest(asset_key=request.asset_key, context=context), timeout=5)
        except grpc.RpcError as error:
            assert error.code() == grpc.StatusCode.FAILED_PRECONDITION
        else:
            raise AssertionError("corrupt split record accepted")
        print("PASS split-record digest tampering rejected")
    print("PUBLISHED_CONTENT_RPC_PROBE_PASS (synthetic assets; no model/UI/deployment)")


if __name__ == "__main__":
    main()
