import os

import pytest

from a2flow_content.errors import ContentError
from a2flow_content.models import (
    ArtifactKind,
    ArtifactOrigin,
    Citation,
    ConfirmManuscriptCommand,
    ConfirmReadingCommand,
    ConfirmTopicCommand,
    CreateProjectCommand,
    Environment,
    ExportFormat,
    ExportManuscriptQuery,
    GetConfirmationQuery,
    GetProjectQuery,
    InputReference,
    ListProjectsQuery,
    Manuscript,
    OutputFormat,
    ReadingBrief,
    ReadingPoint,
    ReferenceKind,
    SaveArtifactCommand,
    SaveSourceCommand,
    TopicOption,
    TopicPlan,
    TrustedContext,
)
from a2flow_content.repository import PostgresContentRepository
from a2flow_content.service import ContentService


def context(user_id: int, request_id: str, env: Environment = Environment.PRT) -> TrustedContext:
    return TrustedContext(user_id, env, request_id)


@pytest.mark.skipif(
    "A2FLOW_CONTENT_TEST_DSN" not in os.environ,
    reason="isolated PostgreSQL not configured",
)
def test_complete_content_kernel() -> None:
    database = os.environ.get("A2FLOW_CONTENT_TEST_DATABASE")
    if not database:
        pytest.fail("A2FLOW_CONTENT_TEST_DATABASE is required")
    repository = PostgresContentRepository(
        os.environ["A2FLOW_CONTENT_TEST_DSN"],
        environment=Environment.PRT,
        database=database,
    )
    repository.setup()
    repository.check_ready()
    service = ContentService(repository)
    user_id = 9_007_199_254_740_993

    create_context = context(user_id, "create-project")
    create = CreateProjectCommand("注意力练习", "职场新人", OutputFormat.ARTICLE)
    project = service.create_project(create_context, create)
    assert service.create_project(create_context, create) == project
    with pytest.raises(ContentError, match="IDEMPOTENCY_CONFLICT"):
        service.create_project(
            create_context,
            CreateProjectCommand("另一标题", "职场新人", OutputFormat.ARTICLE),
        )

    source_command = SaveSourceCommand(
        project.id,
        "读书笔记",
        "注意力不是无限资源。主动安排休息能保护注意力。",
        "https://example.invalid/note",
    )
    source_context = context(user_id, "save-source")
    source = service.save_source(source_context, source_command)
    assert service.save_source(source_context, source_command) == source
    source_ref = InputReference(ReferenceKind.SOURCE, source.id, source.revision)
    current = service.get_project(
        context(user_id, "project-after-source"), GetProjectQuery(project.id)
    )
    assert current.current_source_id == source.id and current.revision == 2

    brief = ReadingBrief(
        (
            ReadingPoint(
                "p1",
                "注意力有限",
                "注意力不是无限资源",
                "第一句",
                "需要有意识分配",
            ),
        )
    )
    brief_record = service.save_artifact(
        context(user_id, "save-brief"),
        SaveArtifactCommand(
            project.id,
            ArtifactKind.READING_BRIEF,
            brief,
            (source_ref,),
            ArtifactOrigin.MODEL_GENERATED,
        ),
    )
    with pytest.raises(ContentError, match="EVIDENCE_NOT_IN_REFERENCED_SOURCE"):
        service.save_artifact(
            context(user_id, "bad-brief"),
            SaveArtifactCommand(
                project.id,
                ArtifactKind.READING_BRIEF,
                ReadingBrief((ReadingPoint("p2", "虚构", "不存在的原文", None, "无"),)),
                (source_ref,),
                ArtifactOrigin.MODEL_GENERATED,
            ),
        )

    confirm_context = context(user_id, "confirm-reading")
    with pytest.raises(ContentError, match="UNKNOWN_SELECTED_POINT"):
        service.confirm_reading(
            confirm_context,
            ConfirmReadingCommand(project.id, brief_record.id, ("missing",), None),
        )
    reading = service.confirm_reading(
        confirm_context,
        ConfirmReadingCommand(project.id, brief_record.id, ("p1",), "个人理解"),
    )
    assert reading.selection.selected_point_ids == ("p1",)
    assert (
        service.get_confirmation(
            context(user_id, "get-reading-confirmation"),
            GetConfirmationQuery(reading.id),
        )
        == reading
    )

    brief_ref = InputReference(ReferenceKind.ARTIFACT, brief_record.id, brief_record.revision)
    topic_record = service.save_artifact(
        context(user_id, "save-topic"),
        SaveArtifactCommand(
            project.id,
            ArtifactKind.TOPIC_PLAN,
            TopicPlan(
                (
                    TopicOption(
                        "t1",
                        "注意力不是意志力",
                        "从资源管理切入",
                        "职场新人",
                        "连接工作节奏",
                        ("p1",),
                    ),
                )
            ),
            (brief_ref,),
            ArtifactOrigin.MODEL_GENERATED,
        ),
    )
    service.confirm_topic(
        context(user_id, "confirm-topic"),
        ConfirmTopicCommand(
            project.id,
            topic_record.id,
            "t1",
            "注意力不是意志力",
            "从资源管理切入",
        ),
    )

    topic_ref = InputReference(ReferenceKind.ARTIFACT, topic_record.id, topic_record.revision)
    manuscript_record = service.save_artifact(
        context(user_id, "save-manuscript"),
        SaveArtifactCommand(
            project.id,
            ArtifactKind.MANUSCRIPT,
            Manuscript(
                "注意力不是意志力",
                "# 注意力不是意志力\n\n主动安排休息。",
                (Citation(ReferenceKind.SOURCE, source.id, source.revision, "读书笔记"),),
            ),
            (source_ref, topic_ref),
            ArtifactOrigin.USER_EDITED,
        ),
    )
    service.confirm_manuscript(
        context(user_id, "confirm-manuscript"),
        ConfirmManuscriptCommand(project.id, manuscript_record.id),
    )
    markdown = service.export_manuscript(
        context(user_id, "export-md"),
        ExportManuscriptQuery(manuscript_record.id, ExportFormat.MARKDOWN),
    )
    plain = service.export_manuscript(
        context(user_id, "export-txt"),
        ExportManuscriptQuery(manuscript_record.id, ExportFormat.TXT),
    )
    assert markdown.filename.endswith(".md") and markdown.content.startswith("# ")
    assert plain.filename.endswith(".txt")
    assert plain.content.startswith("注意力不是意志力")
    page = service.list_projects(context(user_id, "list"), ListProjectsQuery())
    assert page.total == 1 and page.items[0].revision == 5

    with pytest.raises(ContentError, match="CONTENT_NOT_FOUND"):
        service.get_project(context(user_id + 1, "foreign"), GetProjectQuery(project.id))
    replacement = service.save_source(
        context(user_id, "replace-source"),
        SaveSourceCommand(project.id, "新版本", "显式保存的新版本", None),
    )
    assert replacement.revision == 2
    replaced_project = service.get_project(
        context(user_id, "after-replace"), GetProjectQuery(project.id)
    )
    assert replaced_project.revision == 6
    with pytest.raises(ContentError, match="ENVIRONMENT_MISMATCH"):
        service.get_project(
            context(user_id, "wrong-env", Environment.ONLINE),
            GetProjectQuery(project.id),
        )

    other = service.create_project(
        context(user_id, "other-project"),
        CreateProjectCommand("其他项目", "其他读者", OutputFormat.SPOKEN_SCRIPT),
    )
    with pytest.raises(ContentError, match="INPUT_REFERENCE_NOT_FOUND"):
        service.save_artifact(
            context(user_id, "cross-project"),
            SaveArtifactCommand(
                other.id,
                ArtifactKind.READING_BRIEF,
                brief,
                (source_ref,),
                ArtifactOrigin.MODEL_GENERATED,
            ),
        )
