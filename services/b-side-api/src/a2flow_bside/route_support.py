"""Shared HTTP formatting and worker-stream bridge; no service lookup."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import queue
import threading
from collections.abc import AsyncIterator, Iterator

from .errors import BsideError
from .route_dependencies import JsonObject


def _iterate_thread(sync_iter: Iterator[str]) -> AsyncIterator[str]:
    """Pump a blocking generator into an async stream from a worker thread."""
    pending: queue.Queue[tuple[str, str | Exception | None]] = queue.Queue()

    def produce() -> None:
        try:
            for chunk in sync_iter:
                pending.put(("chunk", chunk))
            pending.put(("done", None))
        except Exception as exc:  # noqa: BLE001
            pending.put(("error", exc))

    threading.Thread(target=produce, daemon=True).start()

    async def consume() -> AsyncIterator[str]:
        while True:
            kind, payload = await asyncio.to_thread(pending.get)
            if kind == "chunk":
                assert isinstance(payload, str)
                yield payload
            elif kind == "error":
                assert isinstance(payload, Exception)
                raise payload
            else:
                return

    return consume()


def _iso(value: object) -> object:
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _iso(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_iso(item) for item in value]
    return value


def _bounded_run_reference(snapshot: JsonObject) -> JsonObject:
    """Bound the final JSON attachment, including escaped strings and metadata."""
    frozen = {key: value for key, value in snapshot.items() if key != "outputs"}
    page = frozen["resultPage"]

    def encoded_size(value: JsonObject) -> int:
        try:
            return len(
                json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            )
        except (TypeError, ValueError) as error:
            raise BsideError("INVALID_RUN_REFERENCE_RESULT", 502) from error

    if encoded_size(frozen) <= 11000:
        return frozen

    def shortened(length: int) -> JsonObject:
        return {
            **frozen,
            "resultPage": page[:length],
            "truncated": True,
            "nextOffset": frozen.get("resultOffset", 0) + length,
        }

    if encoded_size(shortened(0)) > 11000:
        raise BsideError("RUN_REFERENCE_METADATA_TOO_LARGE", 413)
    low, high = 0, len(page)
    while low < high:
        middle = (low + high + 1) // 2
        if encoded_size(shortened(middle)) <= 11000:
            low = middle
        else:
            high = middle - 1
    return shortened(low)


def _schedule_json(row: JsonObject) -> JsonObject:
    return {
        "id": row["id"],
        "workflowKey": row["workflow_key"],
        "environment": row["environment"],
        "ruleType": row["rule_type"],
        "ruleJson": row["rule_json"],
        "timezone": row["timezone"],
        "inputText": row["input_text"],
        "enabled": row["enabled"],
        "nextRunAt": _iso(row["next_run_at"]),
        "lastRunAt": _iso(row["last_run_at"]),
        "createdAt": _iso(row["created_at"]),
    }
