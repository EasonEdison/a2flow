"""Neutral state vocabulary; waiting for an action ends a turn, not a business task."""

from enum import StrEnum
from typing import Literal


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


ContinuationDisplayStatus = Literal["RUNNING", "COMPLETED", "NEEDS_REVIEW", "FAILED", "UNKNOWN"]


def continuation_status_from_delivery(delivery: object) -> ContinuationDisplayStatus:
    """Only product delivery state; never use this as business-resolution evidence."""
    if delivery in ("completed", "waiting_action"):
        return "COMPLETED"
    if delivery in ("queued", "running"):
        return "RUNNING"
    if delivery == "unconfirmed":
        return "NEEDS_REVIEW"
    if delivery == "failed":
        return "FAILED"
    return "UNKNOWN"
