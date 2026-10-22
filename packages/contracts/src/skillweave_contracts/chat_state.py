"""Neutral state vocabulary; waiting for an action ends a turn, not a business task."""

from enum import StrEnum


class TurnSource(StrEnum):
    USER_MESSAGE = "USER_MESSAGE"
    PROCESSING = "PROCESSING"
    CARD_CONTINUATION = "CARD_CONTINUATION"


class ProductTurnStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ContinuationStatus(StrEnum):
    PENDING = "PENDING"
    MATERIALIZED = "MATERIALIZED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


FINAL_DELIVERIES = frozenset({"completed", "waiting_action"})


def delivery_turn_status(delivery: object) -> str:
    """Only product delivery state; never use this as business-resolution evidence."""
    if delivery in ("completed", "waiting_action"):
        return ProductTurnStatus.COMPLETED.value
    if delivery in ("queued", "running"):
        return ProductTurnStatus.RUNNING.value
    if delivery == "unconfirmed":
        return ProductTurnStatus.NEEDS_REVIEW.value
    if delivery == "failed":
        return "FAILED"
    return "UNKNOWN"
