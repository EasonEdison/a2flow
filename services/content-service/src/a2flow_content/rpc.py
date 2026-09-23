"""Thin typed protobuf boundary; business rules and transactions stay in ContentService."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

import grpc
from a2flow.capability.v1 import capability_pb2 as cap
from a2flow.content.v1 import content_pb2 as pb
from a2flow.content.v1 import content_pb2_grpc as rpc

from . import models as m
from .errors import ContentError
from .service import ContentService

T = TypeVar("T")
LOG = logging.getLogger(__name__)


def trusted(request: cap.ExecutionContext) -> m.TrustedContext:
    if not request.HasField("user_id") or request.client not in ("PC", "APP"):
        raise ContentError("INVALID_TRUSTED_CONTEXT", 401)
    return m.TrustedContext(
        request.user_id,
        m.Environment(cap.Environment.Name(request.environment)),
        request.request_id,
    )


def input_body(body: pb.ArtifactBody) -> m.ArtifactBody:
    kind = body.WhichOneof("value")
    if kind == "reading_brief":
        return m.ReadingBrief(
            tuple(
                m.ReadingPoint(
                    p.id,
                    p.claim,
                    p.evidence_quote if p.HasField("evidence_quote") else None,
                    p.evidence_locator if p.HasField("evidence_locator") else None,
                    p.explanation,
                    p.model_suggestion,
                )
                for p in body.reading_brief.points
            ),
            tuple(body.reading_brief.questions),
            tuple(body.reading_brief.usable_materials),
        )
    if kind == "topic_plan":
        return m.TopicPlan(
            tuple(
                m.TopicOption(
                    t.id, t.title, t.angle, t.audience, t.rationale, tuple(t.source_point_ids)
                )
                for t in body.topic_plan.topics
            )
        )
    if kind == "manuscript":
        item = body.manuscript
        return m.Manuscript(
            item.title,
            item.body_markdown,
            tuple(
                m.Citation(
                    m.ReferenceKind(c.reference_kind),
                    m.uuid_value(c.reference_id, "REFERENCE_ID"),
                    c.revision,
                    c.label,
                )
                for c in item.citations
            ),
        )
    raise ContentError("ARTIFACT_BODY_REQUIRED")


def output_body(body: m.ArtifactBody) -> pb.ArtifactBody:
    if isinstance(body, m.ReadingBrief):
        return pb.ArtifactBody(
            reading_brief=pb.ReadingBrief(
                points=[
                    pb.ReadingPoint(
                        id=p.id,
                        claim=p.claim,
                        evidence_quote=p.evidence_quote,
                        evidence_locator=p.evidence_locator,
                        explanation=p.explanation,
                        model_suggestion=p.model_suggestion,
                    )
                    for p in body.points
                ],
                questions=body.questions,
                usable_materials=body.usable_materials,
            )
        )
    if isinstance(body, m.TopicPlan):
        return pb.ArtifactBody(
            topic_plan=pb.TopicPlan(
                topics=[
                    pb.TopicOption(
                        id=t.id,
                        title=t.title,
                        angle=t.angle,
                        audience=t.audience,
                        rationale=t.rationale,
                        source_point_ids=t.source_point_ids,
                    )
                    for t in body.topics
                ]
            )
        )
    return pb.ArtifactBody(
        manuscript=pb.Manuscript(
            title=body.title,
            body_markdown=body.body_markdown,
            citations=[
                pb.Citation(
                    reference_kind=c.reference_kind.value,
                    reference_id=str(c.reference_id),
                    revision=c.revision,
                    label=c.label,
                )
                for c in body.citations
            ],
        )
    )


def project(record: m.ProjectRecord) -> pb.Project:
    return pb.Project(
        id=str(record.id),
        title=record.title,
        audience=record.audience,
        output_format=record.output_format.value,
        revision=record.revision,
        current_source_id=str(record.current_source_id) if record.current_source_id else "",
        current_selection_id=str(record.current_selection_id)
        if record.current_selection_id
        else "",
        current_manuscript_id=str(record.current_manuscript_id)
        if record.current_manuscript_id
        else "",
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def source(record: m.SourceRecord) -> pb.Source:
    return pb.Source(
        id=str(record.id),
        project_id=str(record.project_id),
        revision=record.revision,
        title=record.title,
        body=record.body,
        source_url=record.source_url or "",
        digest=record.digest,
        created_at=record.created_at.isoformat(),
    )


def artifact(record: m.ArtifactRecord) -> pb.Artifact:
    return pb.Artifact(
        id=str(record.id),
        project_id=str(record.project_id),
        kind=record.kind.value,
        revision=record.revision,
        body=output_body(record.body),
        body_markdown=record.body_markdown,
        input_refs=[
            pb.InputReference(kind=r.kind.value, id=str(r.id), revision=r.revision)
            for r in record.input_refs
        ],
        origin=record.origin.value,
        created_at=record.created_at.isoformat(),
    )


def confirmation(record: m.ConfirmationRecord) -> pb.Confirmation:
    result = pb.Confirmation(
        id=str(record.id),
        project_id=str(record.project_id),
        artifact_id=str(record.artifact_id),
        decision_type=record.decision_type.value,
        created_at=record.created_at.isoformat(),
    )
    if isinstance(record.selection, m.ReadingSelection):
        result.selected_point_ids.extend(record.selection.selected_point_ids)
        result.user_notes = record.selection.user_notes or ""
    elif isinstance(record.selection, m.TopicSelection):
        result.topic_id = record.selection.topic_id
        result.edited_title = record.selection.edited_title
        result.edited_angle = record.selection.edited_angle
    return result


def invoke(context: grpc.ServicerContext, operation: Callable[[], T]) -> T:
    if not context.is_active():
        context.abort(grpc.StatusCode.CANCELLED, "REQUEST_CANCELLED")
    try:
        return operation()
    except ContentError as error:
        code = {
            400: grpc.StatusCode.INVALID_ARGUMENT,
            401: grpc.StatusCode.UNAUTHENTICATED,
            403: grpc.StatusCode.PERMISSION_DENIED,
            404: grpc.StatusCode.NOT_FOUND,
            409: grpc.StatusCode.ABORTED,
            413: grpc.StatusCode.RESOURCE_EXHAUSTED,
            503: grpc.StatusCode.UNAVAILABLE,
        }.get(error.status, grpc.StatusCode.INTERNAL)
        context.abort(code, error.code)
    except ValueError:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "INVALID_REQUEST")
    except Exception as error:
        # Never log payloads, connection strings or database exception text.
        LOG.error("Content RPC failed: %s", type(error).__name__)
        context.abort(grpc.StatusCode.INTERNAL, "CONTENT_OPERATION_FAILED")


class ContentRpcService(rpc.ContentServiceServicer):
    def __init__(self, service: ContentService) -> None:
        self.service = service

    def CreateProject(
        self, request: pb.CreateProjectRequest, context: grpc.ServicerContext
    ) -> pb.Project:
        return invoke(
            context,
            lambda: project(
                self.service.create_project(
                    trusted(request.context),
                    m.CreateProjectCommand(
                        request.title, request.audience, m.OutputFormat(request.output_format)
                    ),
                )
            ),
        )

    def ListProjects(
        self, request: pb.ListProjectsRequest, context: grpc.ServicerContext
    ) -> pb.ListProjectsResponse:
        def operation() -> pb.ListProjectsResponse:
            result = self.service.list_projects(
                trusted(request.context), m.ListProjectsQuery(request.page, request.page_size)
            )
            return pb.ListProjectsResponse(
                list=[project(p) for p in result.items],
                total=result.total,
                page=result.page,
                page_size=result.page_size,
            )

        return invoke(context, operation)

    def GetProject(
        self, request: pb.GetProjectRequest, context: grpc.ServicerContext
    ) -> pb.Project:
        return invoke(
            context,
            lambda: project(
                self.service.get_project(
                    trusted(request.context),
                    m.GetProjectQuery(m.uuid_value(request.project_id, "PROJECT_ID")),
                )
            ),
        )

    def SaveSource(self, request: pb.SaveSourceRequest, context: grpc.ServicerContext) -> pb.Source:
        def operation() -> pb.Source:
            if not request.HasField("expected_project_revision"):
                raise ContentError("EXPECTED_PROJECT_REVISION_REQUIRED")
            return source(
                self.service.save_source(
                    trusted(request.context),
                    m.SaveSourceCommand(
                        m.uuid_value(request.project_id, "PROJECT_ID"),
                        request.title,
                        request.body,
                        request.source_url or None,
                        request.expected_project_revision,
                    ),
                )
            )

        return invoke(context, operation)

    def GetSource(self, request: pb.GetSourceRequest, context: grpc.ServicerContext) -> pb.Source:
        return invoke(
            context,
            lambda: source(
                self.service.get_source(
                    trusted(request.context),
                    m.GetSourceQuery(m.uuid_value(request.source_id, "SOURCE_ID")),
                )
            ),
        )

    def SaveArtifact(
        self, request: pb.SaveArtifactRequest, context: grpc.ServicerContext
    ) -> pb.Artifact:
        return invoke(
            context,
            lambda: artifact(
                self.service.save_artifact(
                    trusted(request.context),
                    m.SaveArtifactCommand(
                        m.uuid_value(request.project_id, "PROJECT_ID"),
                        m.ArtifactKind(request.kind),
                        input_body(request.body),
                        tuple(
                            m.InputReference(
                                m.ReferenceKind(r.kind),
                                m.uuid_value(r.id, "REFERENCE_ID"),
                                r.revision,
                            )
                            for r in request.input_refs
                        ),
                        m.ArtifactOrigin(request.origin),
                    ),
                )
            ),
        )

    def GetArtifact(
        self, request: pb.GetArtifactRequest, context: grpc.ServicerContext
    ) -> pb.Artifact:
        return invoke(
            context,
            lambda: artifact(
                self.service.get_artifact(
                    trusted(request.context),
                    m.GetArtifactQuery(m.uuid_value(request.artifact_id, "ARTIFACT_ID")),
                )
            ),
        )

    def GetConfirmation(
        self, request: pb.GetConfirmationRequest, context: grpc.ServicerContext
    ) -> pb.Confirmation:
        return invoke(
            context,
            lambda: confirmation(
                self.service.get_confirmation(
                    trusted(request.context),
                    m.GetConfirmationQuery(
                        m.uuid_value(request.confirmation_id, "CONFIRMATION_ID")
                    ),
                )
            ),
        )

    def ConfirmReading(
        self, request: pb.ConfirmReadingRequest, context: grpc.ServicerContext
    ) -> pb.Confirmation:
        def operation() -> pb.Confirmation:
            if not request.HasField("expected_project_revision"):
                raise ContentError("EXPECTED_PROJECT_REVISION_REQUIRED")
            return confirmation(
                self.service.confirm_reading(
                    trusted(request.context),
                    m.ConfirmReadingCommand(
                        m.uuid_value(request.project_id, "PROJECT_ID"),
                        m.uuid_value(request.artifact_id, "ARTIFACT_ID"),
                        tuple(request.selected_point_ids),
                        request.user_notes or None,
                        request.expected_project_revision,
                    ),
                )
            )

        return invoke(context, operation)

    def ConfirmTopic(
        self, request: pb.ConfirmTopicRequest, context: grpc.ServicerContext
    ) -> pb.Confirmation:
        def operation() -> pb.Confirmation:
            if not request.HasField("expected_project_revision"):
                raise ContentError("EXPECTED_PROJECT_REVISION_REQUIRED")
            return confirmation(
                self.service.confirm_topic(
                    trusted(request.context),
                    m.ConfirmTopicCommand(
                        m.uuid_value(request.project_id, "PROJECT_ID"),
                        m.uuid_value(request.artifact_id, "ARTIFACT_ID"),
                        request.topic_id,
                        request.edited_title,
                        request.edited_angle,
                        request.expected_project_revision,
                    ),
                )
            )

        return invoke(context, operation)

    def ConfirmManuscript(
        self, request: pb.ConfirmManuscriptRequest, context: grpc.ServicerContext
    ) -> pb.Confirmation:
        def operation() -> pb.Confirmation:
            if not request.HasField("expected_project_revision"):
                raise ContentError("EXPECTED_PROJECT_REVISION_REQUIRED")
            return confirmation(
                self.service.confirm_manuscript(
                    trusted(request.context),
                    m.ConfirmManuscriptCommand(
                        m.uuid_value(request.project_id, "PROJECT_ID"),
                        m.uuid_value(request.artifact_id, "ARTIFACT_ID"),
                        request.expected_project_revision,
                    ),
                )
            )

        return invoke(context, operation)

    def ExportManuscript(
        self, request: pb.ExportManuscriptRequest, context: grpc.ServicerContext
    ) -> pb.ExportManuscriptResponse:
        def operation() -> pb.ExportManuscriptResponse:
            result = self.service.export_manuscript(
                trusted(request.context),
                m.ExportManuscriptQuery(
                    m.uuid_value(request.artifact_id, "ARTIFACT_ID"), m.ExportFormat(request.format)
                ),
            )
            return pb.ExportManuscriptResponse(
                filename=result.filename, media_type=result.media_type, content=result.content
            )

        return invoke(context, operation)
