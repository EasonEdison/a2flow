"""Transport-neutral typed content service interface."""

from __future__ import annotations

import re
from typing import Protocol
from uuid import UUID

from markdown_it import MarkdownIt

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
    ListProjectsQuery,
    Manuscript,
    ProjectPage,
    ProjectRecord,
    SaveArtifactCommand,
    SaveSourceCommand,
    SourceRecord,
    TrustedContext,
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
