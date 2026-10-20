"""Stable message identity shared by continuation and processing-task binding."""
from hashlib import sha256
from .errors import BsideError


def continuation_reference(card_id: str, confirmation_request_id: str | None = None) -> str:
    if confirmation_request_id is None:
        return card_id
    if not isinstance(confirmation_request_id, str) or not confirmation_request_id:
        raise BsideError("CHAT_CONTINUATION_UNCONFIRMED", 409)
    return "write:" + sha256((card_id + "\0" + confirmation_request_id).encode()).hexdigest()
