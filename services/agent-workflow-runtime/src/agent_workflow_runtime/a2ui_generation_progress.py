"""Typed, observation-only milestones for one generated-card operation."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import monotonic
from typing import Literal

from .models import ActionRejected

LOG = logging.getLogger(__name__)

GenerationStage = Literal[
    "preparing", "generating", "validating_loading", "saving", "completed", "failed"
]


@dataclass(frozen=True)
class GenerationProgress:
    stage: GenerationStage
    elapsed_ms: int
    error_code: str = ""


GenerationObserver = Callable[[GenerationProgress], None]
_OBSERVER: ContextVar[GenerationObserver | None] = ContextVar(
    "a2flow_generation_observer", default=None
)


@contextmanager
def observe_generation(observer: GenerationObserver) -> Iterator[None]:
    token = _OBSERVER.set(observer)
    try:
        yield
    finally:
        _OBSERVER.reset(token)


def generation_error_code(error: Exception) -> str:
    """Expose only platform codes; provider text can contain private request data."""
    code = str(error) if isinstance(error, ActionRejected) else ""
    if re.fullmatch(r"(?:A2UI_|RPC_)[A-Z0-9_]{1,110}", code):
        return code
    return "A2UI_GENERATION_FAILED"


class GenerationTrace:
    def __init__(self) -> None:
        self._started_at = monotonic()

    def emit(self, stage: GenerationStage, error_code: str = "") -> None:
        observer = _OBSERVER.get()
        if observer is None:
            return
        progress = GenerationProgress(
            stage, max(0, int((monotonic() - self._started_at) * 1000)), error_code
        )
        try:
            observer(progress)
        except Exception as error:
            # A display subscriber must never change the business outcome.
            LOG.warning("A2UI progress delivery failed: kind=%s", type(error).__name__)


@contextmanager
def generation_trace() -> Iterator[GenerationTrace]:
    trace = GenerationTrace()
    trace.emit("preparing")
    try:
        yield trace
    except Exception as error:
        trace.emit("failed", generation_error_code(error))
        raise
