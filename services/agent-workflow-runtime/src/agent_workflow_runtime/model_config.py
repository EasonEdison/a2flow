"""Trusted DeepSeek chat-completions configuration, not client/model ingress."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ModelConfigurationError(RuntimeError):
    """Fixed error codes only; never provider/configuration/credential details."""


class DeepSeekOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    thinking: Literal["enabled", "disabled"] = "enabled"
    reasoning_effort: Literal["low", "high", "max"] | None = None
    max_tokens: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def no_ignored_reasoning_option(self):
        if self.thinking == "disabled" and self.reasoning_effort is not None:
            raise ValueError("reasoning effort requires thinking mode")
        return self

    def sdk_options(self):
        options = {"extra_body": {"thinking": {"type": self.thinking}}}
        if self.reasoning_effort is not None:
            options["reasoning_effort"] = self.reasoning_effort
        if self.max_tokens is not None:
            options["max_tokens"] = self.max_tokens
        return options


class DeepSeekConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model_id: Literal["deepseek-v4-pro", "deepseek-v4-flash"]
    endpoint: Literal["https://api.deepseek.com", "https://api.deepseek.com/v1"] = Field(
        default="https://api.deepseek.com", repr=False,
    )
    credential_ref: str = Field(min_length=1, max_length=256, repr=False)
    timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    options: DeepSeekOptions = Field(default_factory=DeepSeekOptions, repr=False)

    @property
    def harness_profile_key(self):
        return "deepseek:" + self.model_id


def parse_deepseek_configuration(value):
    try:
        return DeepSeekConfiguration.model_validate(value)
    except (ValidationError, ValueError, TypeError):
        raise ModelConfigurationError("INVALID_DEEPSEEK_CONFIGURATION") from None
