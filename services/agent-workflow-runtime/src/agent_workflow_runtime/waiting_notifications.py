"""Recover waiting notices from native checkpoints without invoking saved graphs."""
from __future__ import annotations

from collections.abc import Callable, Iterator
import json
import logging
from threading import Event, Thread
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from skillweave_contracts import TrustedContext

from .events import DomainEvent, NODE_WAITING
from .lifecycle import RunLifecycle, RunRecord

LOG = logging.getLogger(__name__)


def waiting_references(run: RunRecord, snapshot: Any) -> Iterator[tuple[str, dict[str, str]]]:
    """Read public native tasks/interrupts, including interrupted child graphs."""
    found: dict[tuple[str, str, str], tuple[str, dict[str, str]]] = {}

    def visit(state: Any) -> None:
        for task in state.tasks:
            for pending in task.interrupts:
                value = pending.value
                if not isinstance(value, dict) or value.get("runId") != run.run_id:
                    continue
                keys = ("nodeId", "interactionId", "applicationKey", "versionId")
                if not isinstance(pending.id, str) or not pending.id or any(
                    not isinstance(value.get(key), str) or not value[key] for key in keys
                ):
                    continue
                reference = {key: value[key] for key in keys}
                identity = (reference["nodeId"], reference["interactionId"], pending.id)
                found[identity] = (pending.id, reference)
            if hasattr(task.state, "tasks"):
                visit(task.state)

    visit(snapshot)
    yield from found.values()


def publish_waiting_snapshot(lifecycle: RunLifecycle, run: RunRecord, snapshot: Any) -> int:
    """Publish a checked waiting projection; lifecycle and interaction can only reject it."""
    events = tuple(waiting_references(run, snapshot))
    if not events:
        return 0
    emitted = 0
    with lifecycle.repository.run_scope(run.owner, run.run_id):
        current = lifecycle.repository.get_run(run.owner, run.run_id)
        if current is None or current.status != "RUNNING":
            return 0
        for interrupt_id, reference in events:
            if lifecycle.waiting_validator is not None and not lifecycle.waiting_validator(
                current, reference,
            ):
                continue
            identity = json.dumps([
                "a2flow-native-waiting-v1", str(run.owner.user_id), run.owner.environment,
                run.run_id, reference["nodeId"], reference["interactionId"], interrupt_id,
            ], separators=(",", ":"))
            lifecycle.event_sink.publish(DomainEvent.create(
                NODE_WAITING, run.run_id, run.definition_key,
                run.owner.user_id, run.owner.environment,
                payload={"nodeId": reference["nodeId"]},
                event_id=uuid5(NAMESPACE_URL, identity),
            ))
            emitted += 1
    return emitted


class WaitingNotificationRecovery:
    """One bounded read-only graph at a time, with fair keyset progress and clean shutdown."""

    def __init__(
        self, repository: Any, lifecycle: RunLifecycle,
        execution_session: Callable[..., Any], environment: str,
        *, interval_seconds: float = 30.0, batch_size: int = 3,
    ) -> None:
        if not 1 <= batch_size <= 10 or interval_seconds < 1:
            raise ValueError("INVALID_WAITING_RECOVERY_CONFIGURATION")
        self.repository, self.lifecycle = repository, lifecycle
        self.execution_session, self.environment = execution_session, environment
        self.interval_seconds, self.batch_size = interval_seconds, batch_size
        self._cursor: tuple[int, str] | None = None
        self._stop = Event()
        self._thread: Thread | None = None

    def pass_once(self) -> None:
        candidates = self.repository.waiting_candidates(
            self.environment, after=self._cursor, limit=self.batch_size,
        )
        if not candidates:
            self._cursor = None
            return
        for user_id, run_id in candidates:
            if self._stop.is_set():
                return
            self._cursor = (user_id, run_id)
            owner = TrustedContext(user_id=user_id, environment=self.environment)
            try:
                run = self.lifecycle.read(owner, run_id)
                if run.status != "RUNNING":
                    continue
                with self.execution_session(owner, read_only=True) as session:
                    graph, _ = session.runner.graph_factory(run, self.lifecycle)
                    snapshot = graph.get_state(
                        {"configurable": {"thread_id": run.thread_id}}, subgraphs=True,
                    )
                    publish_waiting_snapshot(self.lifecycle, run, snapshot)
            except Exception as error:
                LOG.warning("Waiting notification recovery failed run_id=%s error_type=%s",
                            run_id, type(error).__name__)

    def _work(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.pass_once()
            except Exception as error:
                LOG.warning("Waiting notification scan failed error_type=%s", type(error).__name__)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("WAITING_RECOVERY_ALREADY_STARTED")
        self._thread = Thread(target=self._work, name="waiting-notification-recovery", daemon=True)
        self._thread.start()

    def shutdown(self, timeout: float = 10.0) -> bool:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            return not self._thread.is_alive()
        return True
