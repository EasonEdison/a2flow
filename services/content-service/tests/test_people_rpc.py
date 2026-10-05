from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import grpc
import pytest
from a2flow.capability.v1 import capability_pb2 as cap
from a2flow.content.v1 import content_pb2 as pb
from a2flow.content.v1 import content_pb2_grpc as rpc

from a2flow_content.rpc import ContentRpcService
from a2flow_content.service import ContentRepository, ContentService


def trusted_context(request_id: str = "people-rpc") -> cap.ExecutionContext:
    return cap.ExecutionContext(
        user_id=12,
        environment=cap.PRT,
        request_id=request_id,
        client="PC",
    )


@pytest.fixture
def people_stub() -> Iterator[rpc.ContentServiceStub]:
    server = grpc.server(ThreadPoolExecutor(max_workers=1))
    service = ContentService(cast(ContentRepository, object()))
    rpc.add_ContentServiceServicer_to_server(ContentRpcService(service), server)
    port = server.add_insecure_port("127.0.0.1:0")
    assert port > 0
    server.start()
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    try:
        yield rpc.ContentServiceStub(channel)
    finally:
        channel.close()
        server.stop(grace=0).wait(timeout=5)


def test_list_people_real_grpc_defaults_and_dynamic_total(
    people_stub: rpc.ContentServiceStub,
) -> None:
    result = people_stub.ListPeople(pb.ListPeopleRequest(context=trusted_context()))

    assert result.total == 15
    assert result.page == 1
    assert result.page_size == 5
    assert [item.person_id for item in result.items] == [
        "demo-person-001",
        "demo-person-002",
        "demo-person-003",
        "demo-person-004",
        "demo-person-005",
    ]


def test_resolve_people_real_grpc_preserves_order(
    people_stub: rpc.ContentServiceStub,
) -> None:
    result = people_stub.ResolvePeople(
        pb.ResolvePeopleRequest(
            context=trusted_context("resolve-people-rpc"),
            person_ids=["demo-person-003", "demo-person-001"],
        )
    )

    assert [item.person_id for item in result.items] == [
        "demo-person-003",
        "demo-person-001",
    ]
    assert result.items[0].name == "苏晚晴"
    assert result.items[1].phone == "138****0001"


def test_people_rpc_rejects_unknown_id_and_untrusted_context(
    people_stub: rpc.ContentServiceStub,
) -> None:
    with pytest.raises(grpc.RpcError) as missing:
        people_stub.ResolvePeople(
            pb.ResolvePeopleRequest(
                context=trusted_context("resolve-missing-rpc"),
                person_ids=["demo-person-999"],
            )
        )
    assert missing.value.code() is grpc.StatusCode.NOT_FOUND
    assert missing.value.details() == "PERSON_NOT_FOUND"

    with pytest.raises(grpc.RpcError) as untrusted:
        people_stub.ListPeople(
            pb.ListPeopleRequest(
                context=cap.ExecutionContext(
                    user_id=12,
                    environment=cap.PRT,
                    request_id="untrusted",
                    client="COMMON",
                )
            )
        )
    assert untrusted.value.code() is grpc.StatusCode.UNAUTHENTICATED
    assert untrusted.value.details() == "INVALID_TRUSTED_CONTEXT"
