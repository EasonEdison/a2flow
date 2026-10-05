# ruff: noqa: RUF001 -- Chinese punctuation in Chinese content fixtures is intentional.
"""Explicit isolated, real-RPC business proof. Never point this at a production database."""

from __future__ import annotations

import argparse
import ipaddress
from collections.abc import Callable
from uuid import uuid4

import grpc
from a2flow.capability.v1 import capability_pb2 as cap
from a2flow.content.v1 import content_pb2 as pb
from a2flow.content.v1 import content_pb2_grpc as rpc

EXPECTED_METHODS = frozenset(
    {
        "CreateProject",
        "ListProjects",
        "ListPeople",
        "ResolvePeople",
        "GetProject",
        "SaveSource",
        "GetSource",
        "SaveArtifact",
        "GetArtifact",
        "GetConfirmation",
        "ConfirmReading",
        "ConfirmTopic",
        "ConfirmManuscript",
        "ExportManuscript",
    }
)


def rejected(call: Callable[[], object], codes: tuple[grpc.StatusCode, ...]) -> None:
    try:
        call()
    except grpc.RpcError as error:
        assert error.code() in codes, error.code()
    else:
        raise AssertionError("request unexpectedly succeeded")


def verify(target: str) -> None:
    host, port = target.rsplit(":", 1)
    if not ipaddress.ip_address(host).is_loopback or not 1 <= int(port) <= 65535:
        raise ValueError("this probe only accepts a literal loopback address")
    prefix = uuid4().hex

    service = pb.DESCRIPTOR.services_by_name["ContentService"]
    methods = frozenset(method.name for method in service.methods)
    assert methods == EXPECTED_METHODS, methods

    def context(operation: str, user_id: int = 2**63 - 1) -> cap.ExecutionContext:
        return cap.ExecutionContext(
            user_id=user_id, environment=cap.PRT, request_id=f"{prefix}:{operation}", client="PC"
        )

    with grpc.insecure_channel(target, options=(("grpc.enable_retries", 0),)) as channel:
        stub = rpc.ContentServiceStub(channel)
        create = pb.CreateProjectRequest(
            context=context("create"),
            title="阅读创作联调",
            audience="新读者",
            output_format="ARTICLE",
        )
        project = stub.CreateProject(create, timeout=10)
        assert stub.CreateProject(create, timeout=10) == project
        rejected(
            lambda: stub.CreateProject(
                pb.CreateProjectRequest(
                    context=context("create"),
                    title="不同载荷",
                    audience="新读者",
                    output_format="ARTICLE",
                ),
                timeout=10,
            ),
            (grpc.StatusCode.ALREADY_EXISTS, grpc.StatusCode.ABORTED),
        )
        page = stub.ListProjects(
            pb.ListProjectsRequest(context=context("list"), page=1, page_size=20), timeout=10
        )
        assert any(item.id == project.id for item in page.list)
        assert page.total >= 1 and page.page == 1 and page.page_size == 20

        people = stub.ListPeople(
            pb.ListPeopleRequest(context=context("people-list")), timeout=10
        )
        assert people.total == 15 and people.page == 1 and people.page_size == 5
        assert len(people.items) == 5 and people.items[0].person_id == "demo-person-001"
        resolved = stub.ResolvePeople(
            pb.ResolvePeopleRequest(
                context=context("people-resolve"),
                person_ids=["demo-person-003", "demo-person-001", "demo-person-003"],
            ),
            timeout=10,
        )
        assert [item.person_id for item in resolved.items] == [
            "demo-person-003",
            "demo-person-001",
        ]
        rejected(
            lambda: stub.ResolvePeople(
                pb.ResolvePeopleRequest(
                    context=context("people-missing"), person_ids=["demo-person-999"]
                ),
                timeout=10,
            ),
            (grpc.StatusCode.NOT_FOUND,),
        )

        source = stub.SaveSource(
            pb.SaveSourceRequest(
                context=context("source"),
                project_id=project.id,
                title="自己的笔记",
                body="专注需要明确目标，也需要安排休息。",
            ),
            timeout=10,
        )
        assert (
            stub.GetSource(
                pb.GetSourceRequest(context=context("source-read"), source_id=source.id), timeout=10
            )
            == source
        )
        source_ref = pb.InputReference(kind="SOURCE", id=source.id, revision=source.revision)
        brief = stub.SaveArtifact(
            pb.SaveArtifactRequest(
                context=context("brief"),
                project_id=project.id,
                kind="READING_BRIEF",
                origin="MODEL_GENERATED",
                input_refs=[source_ref],
                body=pb.ArtifactBody(
                    reading_brief=pb.ReadingBrief(
                        points=[
                            pb.ReadingPoint(
                                id="p1",
                                claim="专注需要明确目标",
                                evidence_quote="专注需要明确目标",
                                evidence_locator="第1段",
                                explanation="先明确当前要完成的事情。",
                            ),
                        ]
                    )
                ),
            ),
            timeout=10,
        )
        reading_request = pb.ConfirmReadingRequest(
            context=context("reading-confirm"),
            project_id=project.id,
            artifact_id=brief.id,
            selected_point_ids=["p1"],
            user_notes="加入我读书时的体会",
        )
        reading = stub.ConfirmReading(reading_request, timeout=10)
        assert list(reading.selected_point_ids) == ["p1"]
        assert stub.ConfirmReading(reading_request, timeout=10) == reading
        topic = stub.SaveArtifact(
            pb.SaveArtifactRequest(
                context=context("topic"),
                project_id=project.id,
                kind="TOPIC_PLAN",
                origin="MODEL_GENERATED",
                input_refs=[
                    pb.InputReference(kind="ARTIFACT", id=brief.id, revision=brief.revision)
                ],
                body=pb.ArtifactBody(
                    topic_plan=pb.TopicPlan(
                        topics=[
                            pb.TopicOption(
                                id="t1",
                                title="先决定读什么",
                                angle="个人读书体验",
                                audience="新读者",
                                rationale="来自已选择的观点",
                                source_point_ids=["p1"],
                            )
                        ]
                    )
                ),
            ),
            timeout=10,
        )
        selection = stub.ConfirmTopic(
            pb.ConfirmTopicRequest(
                context=context("topic-confirm"),
                project_id=project.id,
                artifact_id=topic.id,
                topic_id="t1",
                edited_title="我的读书习惯",
                edited_angle="先明确一个小目标",
            ),
            timeout=10,
        )
        assert selection.topic_id == "t1" and selection.edited_title == "我的读书习惯"
        restored_confirmation = stub.GetConfirmation(
            pb.GetConfirmationRequest(
                context=context("confirmation-read"), confirmation_id=selection.id
            ),
            timeout=10,
        )
        assert restored_confirmation == selection
        rejected(
            lambda: stub.GetConfirmation(
                pb.GetConfirmationRequest(
                    context=context("other-confirmation", -(2**63)),
                    confirmation_id=selection.id,
                ),
                timeout=10,
            ),
            (grpc.StatusCode.NOT_FOUND,),
        )
        text = "# 我的读书习惯\n\n先明确一个小目标，再给自己留出休息时间。"
        manuscript = stub.SaveArtifact(
            pb.SaveArtifactRequest(
                context=context("manuscript"),
                project_id=project.id,
                kind="MANUSCRIPT",
                origin="USER_EDITED",
                input_refs=[
                    source_ref,
                    pb.InputReference(kind="ARTIFACT", id=topic.id, revision=topic.revision),
                ],
                body=pb.ArtifactBody(
                    manuscript=pb.Manuscript(
                        title="我的读书习惯",
                        body_markdown=text,
                        citations=[
                            pb.Citation(
                                reference_kind="SOURCE",
                                reference_id=source.id,
                                revision=source.revision,
                                label="自己的笔记",
                            )
                        ],
                    )
                ),
            ),
            timeout=10,
        )
        final = stub.ConfirmManuscript(
            pb.ConfirmManuscriptRequest(
                context=context("final"),
                project_id=project.id,
                artifact_id=manuscript.id,
            ),
            timeout=10,
        )
        assert final.artifact_id == manuscript.id
        for output_format in ("MARKDOWN", "TXT"):
            exported = stub.ExportManuscript(
                pb.ExportManuscriptRequest(
                    context=context("export"), artifact_id=manuscript.id, format=output_format
                ),
                timeout=10,
            )
            assert exported.content and exported.filename
            if output_format == "MARKDOWN":
                assert exported.content == text
            else:
                assert exported.content.startswith("我的读书习惯")
                assert "# " not in exported.content
        restored = stub.GetArtifact(
            pb.GetArtifactRequest(context=context("artifact-read"), artifact_id=manuscript.id),
            timeout=10,
        )
        assert restored == manuscript
        rejected(
            lambda: stub.GetArtifact(
                pb.GetArtifactRequest(
                    context=context("other", -(2**63)), artifact_id=manuscript.id
                ),
                timeout=10,
            ),
            (grpc.StatusCode.NOT_FOUND,),
        )
        next_source = stub.SaveSource(
            pb.SaveSourceRequest(
                context=context("new-source-version"),
                project_id=project.id,
                title="新的素材版本",
                body="显式保存新的素材版本，不提交项目 revision。",
            ),
            timeout=10,
        )
        assert next_source.id != source.id and next_source.revision == source.revision + 1
        missing = context("missing")
        missing.ClearField("user_id")
        rejected(
            lambda: stub.GetProject(
                pb.GetProjectRequest(context=missing, project_id=project.id), timeout=10
            ),
            (grpc.StatusCode.INVALID_ARGUMENT, grpc.StatusCode.UNAUTHENTICATED),
        )
        other_environment = context("online")
        other_environment.environment = cap.ONLINE
        rejected(
            lambda: stub.GetProject(
                pb.GetProjectRequest(context=other_environment, project_id=project.id), timeout=10
            ),
            (grpc.StatusCode.PERMISSION_DENIED, grpc.StatusCode.FAILED_PRECONDITION),
        )
    print(
        f"CONTENT_RPC_PASS: {len(methods)} methods, confirmations, replay, owner isolation, "
        "revision-free business inputs, environment, export"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--allow-isolated-writes", action="store_true", required=True)
    args = parser.parse_args()
    verify(args.target)
