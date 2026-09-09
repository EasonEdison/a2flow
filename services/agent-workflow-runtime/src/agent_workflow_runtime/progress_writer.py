"""Bounded, process-owned display writer. Never a business execution scheduler."""

from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from threading import Condition, Event, Thread
from time import monotonic
from uuid import uuid4

from .progress_observer import bind_progress


TEXT_KINDS = frozenset({"TEXT_DELTA", "REASONING_DELTA"})
MAX_TEXT = 1024 * 1024
MAX_RECORDS = 2000
QUEUE_BYTES = 4 * 1024 * 1024
QUEUE_ENTRIES = 1024
RESERVED_BYTES = 2048
RESERVED_ENTRIES = 2
MAX_FRAME_BYTES = 16384


FIELDS = {
    "MODEL_STARTED": {"modelCallId"}, "MODEL_RETURNED": {"modelCallId"},
    "MODEL_UNCONFIRMED": {"modelCallId", "code"},
    "REASONING_DELTA": {"modelCallId", "text"}, "TEXT_DELTA": {"modelCallId", "text"},
    "TOOL_STARTED": {"toolOperationId", "toolName"},
    "TOOL_RETURNED": {"toolOperationId", "toolName"},
    "TOOL_INTERRUPTED": {"toolOperationId", "toolName"},
    "TOOL_UNCONFIRMED": {"toolOperationId", "toolName"},
    "NODE_STARTED": {"nodeOperationId"}, "NODE_RETURNED": {"nodeOperationId"},
    "NODE_INTERRUPTED": {"nodeOperationId"}, "NODE_UNCONFIRMED": {"nodeOperationId"},
    "CAPTURE_INCOMPLETE": {"code"},
}


def validate_record(record):
    if type(record) is not dict or set(record) != {"kind", "observedAt", "payload"}:
        raise ValueError("INVALID_DISPLAY_RECORD")
    fields = FIELDS.get(record["kind"])
    payload = record["payload"]
    if fields is None or type(payload) is not dict or set(payload) != fields:
        raise ValueError("INVALID_DISPLAY_RECORD")
    for key, value in payload.items():
        if type(value) is not str or (key != "text" and len(value) > 256):
            raise ValueError("INVALID_DISPLAY_FIELD")
    if datetime.fromisoformat(record["observedAt"]).tzinfo is None:
        raise ValueError("INVALID_DISPLAY_TIME")
    return record


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def text_parts(text, limit=8192):
    data = text.encode("utf-8")
    while data:
        piece = data[:limit].decode("utf-8", errors="ignore")
        if not piece:
            raise ValueError("INVALID_PROGRESS_TEXT")
        used = len(piece.encode("utf-8"))
        yield piece
        data = data[used:]


@dataclass
class Segment:
    scope: object
    binding: dict
    count: int = 0
    text_bytes: int = 0
    failed: bool = False


@dataclass
class Pending:
    segment: Segment
    record: dict | None
    size: int
    created: float
    seal: str | None = None


class ProgressWriter:
    """Call start/shutdown from the host lifespan, not per HTTP subscription.

    The repository has bounded connect/statement/lock deadlines. Shutdown never
    waits indefinitely; abandoned/failed captures remain unsealed/unconfirmed.
    """

    def __init__(self, repository, *, max_text=MAX_TEXT, max_records=MAX_RECORDS,
                 queue_bytes=QUEUE_BYTES, queue_entries=QUEUE_ENTRIES):
        for value, ceiling in ((max_text, MAX_TEXT), (max_records, MAX_RECORDS),
                               (queue_bytes, QUEUE_BYTES), (queue_entries, QUEUE_ENTRIES)):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("INVALID_PROGRESS_CAP")
        self.repository = repository
        self.max_text, self.max_records = max_text, max_records
        self.queue_bytes, self.queue_entries = queue_bytes, queue_entries
        self._condition = Condition()
        self._queue, self._segments = deque(), {}
        self._bytes = self._entries = 0
        self._closing = False
        self._deadline = None
        self._thread = None
        self._ready = Event()

    def start(self):
        with self._condition:
            if self._thread is not None:
                raise RuntimeError("PROGRESS_WRITER_ALREADY_STARTED")
            self._thread = Thread(target=self._work, name="a2flow-progress-writer", daemon=True)
            self._thread.start()
        if not self._ready.wait(1):
            raise RuntimeError("PROGRESS_WRITER_START_TIMEOUT")
        return self

    @contextmanager
    def capture(self, context, node_operation_id=None):
        with bind_progress(context, uuid4().hex, self) as scope:
            scope.node_operation_id = node_operation_id
            outcome = "RETURNED"
            try:
                yield scope
            except BaseException as error:
                from langgraph.errors import GraphInterrupt
                outcome = "INTERRUPTED" if isinstance(error, GraphInterrupt) else "UNCONFIRMED"
                raise
            finally:
                self.finish(scope, outcome)

    def _new(self, scope):
        context = scope.context
        binding = {
            "userId": context.trusted_context.user_id,
            "environment": context.trusted_context.environment,
            "runId": context.invocation_scope.run_id,
            "nodeId": context.invocation_scope.node_id,
            "executionId": scope.execution_id,
            "nodeOperationId": getattr(scope, "node_operation_id", None),
        }
        if len(encoded(binding)) > 1024:
            scope.unavailable = True
            return None
        if (self._bytes + RESERVED_BYTES > self.queue_bytes
                or self._entries + RESERVED_ENTRIES > self.queue_entries):
            scope.unavailable = True
            return None
        segment = Segment(scope, binding)
        self._segments[scope.execution_id] = segment
        self._bytes += RESERVED_BYTES
        self._entries += RESERVED_ENTRIES
        return segment

    def _gap(self, segment, code):
        if segment.failed:
            return
        segment.failed = True
        segment.scope.unavailable = True
        record = {"kind": "CAPTURE_INCOMPLETE", "observedAt": datetime.now(timezone.utc).isoformat(),
                  "payload": {"code": code}}
        # One gap and one seal are accounted for in each active segment's reserve.
        self._queue.append(Pending(segment, record, 0, monotonic()))
        self._condition.notify()

    def offer(self, scope, kind, payload):
        if not self._condition.acquire(blocking=False):
            scope.unavailable = True
            return
        try:
            # An emitter may have passed its outer check before a failed batch
            # removed this segment. Failure is terminal for the same capture.
            if scope.unavailable:
                return
            if self._closing or self._thread is None or not self._thread.is_alive():
                scope.unavailable = True
                return
            segment = self._segments.get(scope.execution_id) or self._new(scope)
            if segment is None or segment.failed:
                return
            if kind in TEXT_KINDS:
                texts = text_parts(payload["text"])
            else:
                texts = (None,)
            for text in texts:
                body = dict(payload)
                if text is not None:
                    body["text"] = text
                text_size = len(text.encode("utf-8")) if text is not None else 0
                now = monotonic()
                record = {"kind": kind, "observedAt": datetime.now(timezone.utc).isoformat(),
                          "payload": body}
                validate_record(record)
                size = len(encoded(record))
                if size > MAX_FRAME_BYTES or segment.text_bytes + text_size > self.max_text:
                    self._gap(segment, "DISPLAY_LIMIT")
                    break
                previous = self._queue[-1] if self._queue else None
                merge = bool(text is not None and previous and previous.segment is segment
                             and previous.record and previous.record["kind"] == kind
                             and previous.record["payload"].get("modelCallId") == body.get("modelCallId")
                             and now - previous.created < .25
                             and len(previous.record["payload"]["text"].encode("utf-8")) + text_size <= 8192)
                if merge:
                    merged = {**previous.record, "payload": {
                        **body, "text": previous.record["payload"]["text"] + text}}
                    difference = len(encoded(merged)) - previous.size
                    if self._bytes + difference > self.queue_bytes:
                        self._gap(segment, "QUEUE_LIMIT")
                        break
                    previous.record, previous.size = merged, previous.size + difference
                    self._bytes += difference
                else:
                    if segment.count >= self.max_records - 1:
                        self._gap(segment, "RECORD_LIMIT")
                        break
                    if self._bytes + size > self.queue_bytes or self._entries + 1 > self.queue_entries:
                        self._gap(segment, "QUEUE_LIMIT")
                        break
                    self._queue.append(Pending(segment, record, size, now))
                    self._bytes += size
                    self._entries += 1
                    segment.count += 1
                segment.text_bytes += text_size
            self._condition.notify()
        finally:
            self._condition.release()

    def finish(self, scope, outcome):
        with self._condition:
            segment = self._segments.get(scope.execution_id)
            if segment is None:
                return  # No displayed operation: no invented execution record.
            if scope.unavailable and not segment.failed:
                self._gap(segment, "CAPTURE_UNAVAILABLE")
            self._queue.append(Pending(segment, None, 0, monotonic(), outcome))
            self._condition.notify()

    def _release(self, segment):
        if self._segments.pop(segment.scope.execution_id, None) is not None:
            self._bytes -= RESERVED_BYTES
            self._entries -= RESERVED_ENTRIES

    def _work(self):
        while True:
            with self._condition:
                self._ready.set()
                if self._closing and (not self._queue or monotonic() >= self._deadline):
                    for segment in self._segments.values():
                        segment.scope.unavailable = True
                    self._queue.clear()
                    self._segments.clear()
                    self._bytes = self._entries = 0
                    return
                if not self._queue:
                    self._condition.wait(.25)
                    continue
                first = self._queue[0]
                if (len(self._queue) == 1 and first.record
                        and first.record["kind"] in TEXT_KINDS and not self._closing):
                    delay = .25 - (monotonic() - first.created)
                    if delay > 0:
                        self._condition.wait(delay)
                        continue
                items = []
                while self._queue and len(items) < 64 and self._queue[0].segment is first.segment:
                    item = self._queue.popleft()
                    items.append(item)
                    if item.seal:
                        break
            segment = first.segment
            records = [item.record for item in items if item.record is not None]
            seal = items[-1].seal
            try:
                self.repository.append(segment.binding, uuid4().hex, records,
                                       seal=seal, incomplete=segment.failed or segment.scope.unavailable)
            except Exception:
                segment.scope.unavailable = True
                segment.failed = True
                # Never retry a business call. One bounded capture-health write;
                # if that also fails, absent/unsealed capture remains unconfirmed.
                try:
                    self.repository.unavailable(segment.binding)
                except Exception:
                    pass
                with self._condition:
                    remaining = deque()
                    for item in self._queue:
                        if item.segment is segment:
                            self._bytes -= item.size
                            if item.size:
                                self._entries -= 1
                        else:
                            remaining.append(item)
                    self._queue = remaining
                    self._release(segment)
            else:
                if seal:
                    with self._condition:
                        self._release(segment)
            finally:
                with self._condition:
                    for item in items:
                        self._bytes -= item.size
                        if item.size:
                            self._entries -= 1

    def shutdown(self, timeout=2.0):
        if not 0 < timeout <= 5:
            raise ValueError("INVALID_DRAIN_TIMEOUT")
        with self._condition:
            self._closing, self._deadline = True, monotonic() + timeout
            self._condition.notify()
        if self._thread:
            self._thread.join(timeout)
        return self._thread is None or not self._thread.is_alive()
