"""Read-only native-message views, not history conversion or HTTP output.

The SDK message remains authoritative. This module cannot recover anything a
provider adapter dropped, establish original wire order, or authorize tool calls.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.messages.content import ContentBlock


@dataclass(frozen=True)
class ModelContentView:
    """Detached SDK projection. Partial blocks are never executable arguments.

    No truncation or custom size limit is applied here. The caller must retain
    the complete native message under its storage/access policy. This internal
    view is not the AF05 safe/public observation schema.
    """

    is_partial: bool
    blocks: tuple[ContentBlock, ...] = field(repr=False)
    message_id: str | None = field(repr=False)
    name: str | None = field(repr=False)
    additional_kwargs: dict[str, Any] = field(repr=False)
    response_metadata: dict[str, Any] = field(repr=False)
    usage_metadata: dict[str, Any] | None = field(repr=False)
    native_extensions: dict[str, Any] = field(repr=False)


def model_content_view(message: AIMessage) -> ModelContentView:
    """Copy public SDK fields without changing, serializing or replacing history.

    Block order is the SDK's projection order, not a claim about transport order.
    Extension data is opaque: no interpretation or automatic outbound forwarding.
    """

    if not isinstance(message, AIMessage):
        raise TypeError("AI_MESSAGE_REQUIRED")
    return ModelContentView(
        is_partial=isinstance(message, AIMessageChunk),
        blocks=tuple(deepcopy(message.content_blocks)),
        message_id=message.id,
        name=message.name,
        additional_kwargs=deepcopy(message.additional_kwargs),
        response_metadata=deepcopy(message.response_metadata),
        usage_metadata=deepcopy(message.usage_metadata),
        native_extensions=deepcopy(message.model_extra or {}),
    )
