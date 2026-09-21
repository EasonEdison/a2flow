"""Strict HTTP request DTOs for the management adapter."""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, JsonValue
from skillweave_contracts.user_id import user_id_from_wire

from .contracts import PublicationTarget


class ClosedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SaveDraft(ClosedRequest):
    expectedRevision: int = Field(ge=0)
    document: dict[str, JsonValue]


class CompareDraft(ClosedRequest):
    document: dict[str, JsonValue]


class WorkspaceFile(ClosedRequest):
    expectedWorkspaceRevision: int = Field(ge=0)
    logicalPath: str = Field(min_length=1, max_length=256)
    mediaType: str = Field(min_length=1, max_length=256)
    base64: str


class WorkspaceDelete(ClosedRequest):
    expectedWorkspaceRevision: int = Field(ge=0)
    logicalPath: str = Field(min_length=1, max_length=256)


class WorkspaceCommit(ClosedRequest):
    expectedWorkspaceRevision: int = Field(ge=0)
    expectedDraftRevision: int = Field(ge=0)


class Target(ClosedRequest):
    environment: str
    versionId: str = Field(min_length=1, max_length=256)
    channel: str
    grayUserIds: list[Annotated[int, BeforeValidator(user_id_from_wire)]] = Field(
        default_factory=list, max_length=1024
    )

    def to_domain(self) -> PublicationTarget:
        return PublicationTarget.create(
            self.environment,
            self.versionId,
            self.channel,
            tuple(self.grayUserIds),
        )


class PreparePublication(ClosedRequest):
    expectedRevision: int = Field(ge=0)
    target: Target


class PublishCandidate(ClosedRequest):
    expectedServingDigest: str = Field(min_length=71, max_length=71)
    candidate: dict[str, JsonValue]
    target: Target


class RollbackSelection(ClosedRequest):
    expectedServingDigest: str = Field(min_length=71, max_length=71)
    target: Target


class ReleaseCandidate(PublishCandidate):
    expectedRevision: int = Field(ge=0)
