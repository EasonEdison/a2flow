"""Transport-neutral typed content service interface."""

from __future__ import annotations

import re
from typing import Protocol
from uuid import UUID

from markdown_it import MarkdownIt

from .errors import ContentError
from .models import (
    ArtifactRecord,
    ConfirmationRecord,
    ConfirmManuscriptCommand,
    ConfirmReadingCommand,
    ConfirmTopicCommand,
    CreateProjectCommand,
    ExportedManuscript,
    ExportFormat,
    ExportManuscriptQuery,
    GetArtifactQuery,
    GetConfirmationQuery,
    GetProjectQuery,
    GetSourceQuery,
    ListPeopleQuery,
    ListProjectsQuery,
    Manuscript,
    PeoplePage,
    PersonRecord,
    ProjectPage,
    ProjectRecord,
    ResolvePeopleQuery,
    SaveArtifactCommand,
    SaveSourceCommand,
    SourceRecord,
    TrustedContext,
)

_DEMO_PEOPLE: tuple[PersonRecord, ...] = (
    PersonRecord("demo-person-001", "林知夏", "138****0001", "女", 26, ("阅读", "徒步")),
    PersonRecord("demo-person-002", "周远舟", "138****0002", "男", 31, ("摄影", "咖啡")),
    PersonRecord("demo-person-003", "苏晚晴", "138****0003", "女", 24, ("绘画", "音乐")),
    PersonRecord("demo-person-004", "陈星野", "138****0004", "男", 29, ("跑步", "电影")),
    PersonRecord("demo-person-005", "赵清禾", "138****0005", "女", 35, ("园艺", "烘焙")),
    PersonRecord("demo-person-006", "陆时安", "138****0006", "男", 28, ("骑行", "旅行")),
    PersonRecord("demo-person-007", "唐予宁", "138****0007", "女", 32, ("瑜伽", "阅读")),
    PersonRecord("demo-person-008", "江砚", "138****0008", "男", 27, ("书法", "桌游")),
    PersonRecord("demo-person-009", "沈听澜", "138****0009", "女", 30, ("游泳", "摄影")),
    PersonRecord("demo-person-010", "顾南乔", "138****0010", "女", 25, ("舞蹈", "旅行")),
    PersonRecord("demo-person-011", "宋屿", "138****0011", "男", 34, ("钓鱼", "烹饪")),
    PersonRecord("demo-person-012", "白芷", "138****0012", "女", 23, ("手工", "动漫")),
    PersonRecord("demo-person-013", "许观澜", "138****0013", "男", 36, ("登山", "历史")),
    PersonRecord("demo-person-014", "温言", "138****0014", "男", 33, ("音乐", "健身")),
    PersonRecord("demo-person-015", "夏木", "138****0015", "女", 27, ("露营", "写作")),
)


class ContentRepository(Protocol):
    def create_project(
        self, context: TrustedContext, title: str, audience: str, output_format: str
    ) -> ProjectRecord: ...

    def list_projects(self, context: TrustedContext, query: ListProjectsQuery) -> ProjectPage: ...

    def get_project(self, context: TrustedContext, project_id: UUID) -> ProjectRecord: ...

    def save_source(self, context: TrustedContext, command: SaveSourceCommand) -> SourceRecord: ...

    def get_source(self, context: TrustedContext, source_id: UUID) -> SourceRecord: ...

    def save_artifact(
        self, context: TrustedContext, command: SaveArtifactCommand
    ) -> ArtifactRecord: ...

    def get_artifact(self, context: TrustedContext, artifact_id: UUID) -> ArtifactRecord: ...

    def get_confirmation(
        self, context: TrustedContext, confirmation_id: UUID
    ) -> ConfirmationRecord: ...

    def confirm_reading(
        self, context: TrustedContext, command: ConfirmReadingCommand
    ) -> ConfirmationRecord: ...

    def confirm_topic(
        self, context: TrustedContext, command: ConfirmTopicCommand
    ) -> ConfirmationRecord: ...

    def confirm_manuscript(
        self, context: TrustedContext, command: ConfirmManuscriptCommand
    ) -> ConfirmationRecord: ...

    def export_manuscript(self, context: TrustedContext, artifact_id: UUID) -> ArtifactRecord: ...


class ContentService:
    def __init__(self, repository: ContentRepository) -> None:
        self._repository = repository

    def create_project(
        self, context: TrustedContext, command: CreateProjectCommand
    ) -> ProjectRecord:
        return self._repository.create_project(
            context, command.title, command.audience, command.output_format.value
        )

    def list_projects(self, context: TrustedContext, query: ListProjectsQuery) -> ProjectPage:
        return self._repository.list_projects(context, query)

    def list_people(self, context: TrustedContext, query: ListPeopleQuery) -> PeoplePage:
        # Identity remains part of this read boundary even though every trusted user sees the
        # same explicitly fictional demo dataset.
        if not isinstance(context, TrustedContext):
            raise TypeError("trusted context required")
        start = (query.page - 1) * query.page_size
        return PeoplePage(
            items=_DEMO_PEOPLE[start : start + query.page_size],
            total=len(_DEMO_PEOPLE),
            page=query.page,
            page_size=query.page_size,
        )

    def resolve_people(
        self, context: TrustedContext, query: ResolvePeopleQuery
    ) -> tuple[PersonRecord, ...]:
        if not isinstance(context, TrustedContext):
            raise TypeError("trusted context required")
        people_by_id = {person.person_id: person for person in _DEMO_PEOPLE}
        items: list[PersonRecord] = []
        for person_id in query.person_ids:
            person = people_by_id.get(person_id)
            if person is None:
                raise ContentError("PERSON_NOT_FOUND", 404)
            items.append(person)
        return tuple(items)

    def get_project(self, context: TrustedContext, query: GetProjectQuery) -> ProjectRecord:
        return self._repository.get_project(context, query.project_id)

    def save_source(self, context: TrustedContext, command: SaveSourceCommand) -> SourceRecord:
        return self._repository.save_source(context, command)

    def get_source(self, context: TrustedContext, query: GetSourceQuery) -> SourceRecord:
        return self._repository.get_source(context, query.source_id)

    def save_artifact(
        self, context: TrustedContext, command: SaveArtifactCommand
    ) -> ArtifactRecord:
        return self._repository.save_artifact(context, command)

    def get_artifact(self, context: TrustedContext, query: GetArtifactQuery) -> ArtifactRecord:
        return self._repository.get_artifact(context, query.artifact_id)

    def get_confirmation(
        self, context: TrustedContext, query: GetConfirmationQuery
    ) -> ConfirmationRecord:
        return self._repository.get_confirmation(context, query.confirmation_id)

    def confirm_reading(
        self, context: TrustedContext, command: ConfirmReadingCommand
    ) -> ConfirmationRecord:
        return self._repository.confirm_reading(context, command)

    def confirm_topic(
        self, context: TrustedContext, command: ConfirmTopicCommand
    ) -> ConfirmationRecord:
        return self._repository.confirm_topic(context, command)

    def confirm_manuscript(
        self, context: TrustedContext, command: ConfirmManuscriptCommand
    ) -> ConfirmationRecord:
        return self._repository.confirm_manuscript(context, command)

    def export_manuscript(
        self, context: TrustedContext, query: ExportManuscriptQuery
    ) -> ExportedManuscript:
        artifact = self._repository.export_manuscript(context, query.artifact_id)
        if not isinstance(artifact.body, Manuscript):
            raise AssertionError("repository returned a non-manuscript")
        safe_title = re.sub(r"[^\w\u3400-\u9fff-]+", "-", artifact.body.title).strip("-")
        safe_title = safe_title[:80] or "manuscript"
        if query.format is ExportFormat.MARKDOWN:
            return ExportedManuscript(
                f"{safe_title}.md", "text/markdown; charset=utf-8", artifact.body.body_markdown
            )
        return ExportedManuscript(
            f"{safe_title}.txt",
            "text/plain; charset=utf-8",
            markdown_to_text(artifact.body.body_markdown),
        )


def markdown_to_text(markdown: str) -> str:
    """Render CommonMark tokens to text while preserving literal code content."""
    blocks: list[str] = []
    for token in MarkdownIt("commonmark").parse(markdown):
        if token.type in {"fence", "code_block"}:
            blocks.append(token.content.rstrip("\n"))
            continue
        if token.type == "hr":
            blocks.append("---")
            continue
        if token.type != "inline" or token.children is None:
            continue
        chunks: list[str] = []
        for child in token.children:
            if child.type in {"text", "code_inline"}:
                chunks.append(child.content)
            elif child.type in {"softbreak", "hardbreak"}:
                chunks.append("\n")
            elif child.type == "image":
                chunks.append(child.content)
        blocks.append("".join(chunks))
    return "\n\n".join(block for block in blocks if block)
