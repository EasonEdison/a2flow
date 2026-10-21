"""Validated HTTP request models, independent of service composition."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from skillweave_contracts.user_id import user_id_from_wire


class MemoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    text: str = Field(min_length=1, max_length=1000)


class MemorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)
    enabled: bool
    entries: list[MemoryEntry] = Field(max_length=20)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class RunReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    activityId: str = Field(min_length=1, max_length=256)


class ProcessingTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    activityId: str = Field(min_length=1, max_length=256)
    attentionId: str = Field(min_length=1, max_length=256)


class ProcessingResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str = Field(min_length=1, max_length=2000)


class MessageSend(BaseModel):
    conversationId: int = Field(gt=0)
    clientRequestId: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    text: str = Field(min_length=1, max_length=4000)
    runReferences: list[RunReference] = Field(default_factory=list, max_length=3)

    processingTarget: ProcessingTarget | None = None
    processingTaskId: str | None = Field(default=None, min_length=1, max_length=128)
    processingRequestId: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_.:-]{1,128}$"
    )

    @model_validator(mode="after")
    def processing_target(self) -> Self:
        if self.processingTarget is not None and self.processingTaskId is not None:
            raise ValueError("PROCESSING_TARGET_CONFLICT")
        if bool(self.processingTarget or self.processingTaskId) != bool(
            self.processingRequestId
        ):
            raise ValueError("PROCESSING_REQUEST_ID_REQUIRED")
        return self

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("MESSAGE_TEXT_REQUIRED")
        return value


class RunStart(BaseModel):
    sourceType: Literal["manual", "chat"] = "manual"
    workflowKey: str = Field(min_length=1, max_length=256)
    input: dict[str, object] | str


class RunRefCreate(BaseModel):
    runId: str = Field(min_length=1, max_length=256)


class InternalRunStart(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requestId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    environment: str = Field(pattern=r"^(PRT|ONLINE)$")
    userId: int
    workflowKey: str = Field(min_length=1, max_length=256)
    input: dict[str, object] | str

    @field_validator("userId", mode="before")
    @classmethod
    def parse_user_id(cls, value: object) -> int:
        return user_id_from_wire(value)


class RunAction(BaseModel):
    nodeId: str = Field(min_length=1, max_length=256)
    interactionId: str = Field(min_length=1, max_length=256)
    actionName: str = Field(min_length=1, max_length=256)
    inputs: dict[str, object] = Field(default_factory=dict)


class ChatCardAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requestId: str = Field(min_length=1, max_length=128)
    actionName: str = Field(min_length=1, max_length=128)
    inputs: dict[str, object]


class WorkflowCardAction(ChatCardAction):
    nodeId: str = Field(min_length=1, max_length=256)
    interactionId: str = Field(min_length=1, max_length=256)


class InternalResume(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    userId: int
    environment: Literal["PRT", "ONLINE"]
    requestId: str = Field(min_length=1, max_length=128)
    actionRequestId: str = Field(min_length=1, max_length=128)
    nodeId: str = Field(min_length=1, max_length=256)
    interactionId: str = Field(min_length=1, max_length=256)

    @field_validator("userId", mode="before")
    @classmethod
    def parse_user_id(cls, value: object) -> int:
        return user_id_from_wire(value)


class CronRuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expression: str = Field(min_length=1, max_length=128)


class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workflowKey: str = Field(min_length=1, max_length=256)
    ruleType: Literal["cron"]
    ruleJson: CronRuleInput
    timezone: str | None = Field(default=None, max_length=64)
    inputText: str = Field(min_length=1, max_length=4000)


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool | None = None
    ruleType: Literal["cron"] | None = None
    ruleJson: CronRuleInput | None = None
    timezone: str | None = Field(default=None, max_length=64)
    inputText: str | None = Field(default=None, min_length=1, max_length=4000)
