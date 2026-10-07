"""Typed scheduler commands. JSON exists only at the transport boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class CommandModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class UserCommand(CommandModel):
    user_id: Annotated[int, Field(gt=0, le=9223372036854775807)]

    @field_validator("user_id", mode="before")
    @classmethod
    def parse_user_id(cls, value: object) -> object:
        if isinstance(value, str) and value.isascii() and value.isdecimal():
            return int(value)
        return value

    @field_serializer("user_id", when_used="json")
    def serialize_user_id(self, value: int) -> str:
        return str(value)


class StartWorkflow(UserCommand):
    kind: Literal["start_workflow"] = "start_workflow"
    message_id: Annotated[str, Field(min_length=1, max_length=200)]
    schedule_id: Annotated[int, Field(gt=0)]
    scheduled_at: datetime
    environment: Literal["PRT", "ONLINE"]
    workflow_key: Annotated[str, Field(min_length=1, max_length=256)]
    input_text: str

    @field_validator("scheduled_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("scheduled_at must include a timezone")
        return value


class ResumeWorkflow(CommandModel):
    kind: Literal["resume_workflow"] = "resume_workflow"
    message_id: Annotated[str, Field(min_length=1, max_length=200)]
    run_id: Annotated[str, Field(min_length=1)]
    node_id: Annotated[str, Field(min_length=1)]
    interaction_id: Annotated[str, Field(min_length=1)]
    action_request_id: Annotated[str, Field(min_length=1)]


class NotificationCommand(UserCommand):
    kind: Literal["notify"] = "notify"
    message_id: Annotated[str, Field(min_length=1, max_length=200)]
    run_id: Annotated[str, Field(min_length=1)]
    event: Literal["waiting", "completed", "failed", "stopped"]
    title: str
    body: str


WorkflowCommand = Annotated[
    StartWorkflow | ResumeWorkflow | NotificationCommand,
    Field(discriminator="kind"),
]
