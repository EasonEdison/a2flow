"""Redis Streams delivery of durable outbox references, not business payloads.

One consumer group per stream. The database owns message content and execution
deduplication. A successful Redis acknowledgement never proves business success.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import TypeAdapter
from redis import Redis
from redis.exceptions import ResponseError


class StreamChannel(StrEnum):
    WORKFLOW = "workflow"
    NOTIFICATIONS = "notifications"


@dataclass(frozen=True)
class StreamDelivery:
    channel: StreamChannel
    entry_id: str
    message_id: str


_READ_RESULT = TypeAdapter(list[tuple[str, list[tuple[str, dict[str, str]]]]])
_CLAIM_RESULT = TypeAdapter(tuple[str, list[tuple[str, dict[str, str]]], list[str]])


class RedisStreamTransport:
    """Bounded polling; callers commit durable outcomes before acknowledge()."""

    def __init__(
        self,
        client: Redis,
        *,
        namespace: str,
        consumer: str,
        reclaim_idle_ms: int = 300_000,
    ) -> None:
        if not namespace or not consumer or reclaim_idle_ms < 1000:
            raise ValueError("Invalid stream configuration")
        self._client = client
        self._namespace = namespace
        self._consumer = consumer
        self._reclaim_idle_ms = reclaim_idle_ms
        self._group = "workers"
        self._claim_cursors = dict.fromkeys(StreamChannel, "0-0")

    def _key(self, channel: StreamChannel) -> str:
        return f"{self._namespace}:{channel.value}"

    def initialize(self) -> None:
        for channel in StreamChannel:
            try:
                self._client.xgroup_create(self._key(channel), self._group, id="0-0", mkstream=True)
            except ResponseError as exc:
                if not str(exc).startswith("BUSYGROUP "):
                    raise

    def publish(self, channel: StreamChannel, message_id: str) -> None:
        if not message_id or len(message_id) > 200:
            raise ValueError("Invalid durable message id")
        # No MAXLEN: dropping pending entries would lose outstanding work.
        self._client.xadd(self._key(channel), {"message_id": message_id})

    def receive(self, channel: StreamChannel) -> StreamDelivery | None:
        """Read one entry, keeping the worker concurrency at one."""
        cursor, entries, deleted = _CLAIM_RESULT.validate_python(
            self._client.xautoclaim(
                self._key(channel),
                self._group,
                self._consumer,
                self._reclaim_idle_ms,
                self._claim_cursors[channel],
                count=1,
            )
        )
        self._claim_cursors[channel] = cursor
        if deleted:
            raise RuntimeError("Pending stream entries were deleted; reconcile durable outbox")
        if not entries:
            batches = _READ_RESULT.validate_python(
                self._client.xreadgroup(
                    self._group, self._consumer, {self._key(channel): ">"}, count=1
                )
            )
            entries = [entry for _, batch in batches for entry in batch]
        if not entries:
            return None
        entry_id, fields = entries[0]
        if set(fields) != {"message_id"} or not fields["message_id"]:
            raise ValueError(f"Invalid stream envelope at {entry_id}")
        return StreamDelivery(channel, entry_id, fields["message_id"])

    def acknowledge(self, delivery: StreamDelivery) -> None:
        """Call only after durable completion/dedup outcome has committed.

        The transaction also deletes the entry to bound memory. This transport
        owns the only consumer group; fan-out uses separate destination streams.
        """
        with self._client.pipeline(transaction=True) as pipeline:
            pipeline.xack(self._key(delivery.channel), self._group, delivery.entry_id)
            pipeline.xdel(self._key(delivery.channel), delivery.entry_id)
            pipeline.execute()
