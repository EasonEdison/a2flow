"""Swappable work/event queue. v1 implementation is PostgreSQL (SKIP LOCKED).

Callers depend only on the QueueClient protocol; the PostgreSQL implementation
can be replaced by Redis/RabbitMQ without touching callers. Delivery is
at-least-once: consumers must be idempotent (dedup_key on enqueue, guarded
UPDATEs on completion).
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Protocol


# 无效队列调用明确报错, 不能静默丢弃工作项。
class QueueError(Exception):
    """Unrecoverable queue operation failure."""


@dataclasses.dataclass(frozen=True)
# 每次领取返回稳定条目 ID、载荷和尝试次数, 消费者据此追踪重复投递。
class QueueItem:
    item_id: int
    queue: str
    payload: dict[str, Any]
    attempts: int


# 调用方依赖队列协议; 至少一次投递仍要求消费业务具有幂等边界。
class QueueClient(Protocol):
    def enqueue(
        self,
        queue: str,
        payload: dict[str, Any],
        *,
        dedup_key: str | None = None,
    ) -> None: ...

    # 领取提供租约, 不承诺业务恰好执行一次。
    def claim(
        self, queue: str, limit: int = 10, lease_seconds: int = 120
    ) -> list[QueueItem]: ...

    # 完成、续租和失败重入由消费者显式调用, 不能把领取当成已处理。
    def complete(self, item_id: int) -> None: ...

    def extend(self, item_id: int, lease_seconds: int) -> None: ...

    def requeue_failed(self, item_id: int) -> None: ...


class PostgresQueueClient:
    """Queue over the queue_items table; the caller owns the psycopg connection.

    claim() atomically marks rows claimed under SKIP LOCKED and grants a lease
    (claimed_until). Expired leases become claimable again, so a crashed worker
    never permanently loses an item (at-least-once).
    """

    # SKIP LOCKED 原子领取可用条目; 租约过期会再次可领, 所以不能直接等同业务重试授权。
    _CLAIM_SQL = """
        WITH candidates AS (
            SELECT id
            FROM queue_items
            WHERE queue = %s
              AND (state = 'pending'
                   OR (state = 'claimed' AND claimed_until <= now()))
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT %s
        )
        UPDATE queue_items AS item
        SET state = 'claimed',
            claimed_until = now() + make_interval(secs => %s),
            attempts = attempts + 1
        FROM candidates
        WHERE item.id = candidates.id
        RETURNING item.id, item.queue, item.payload, item.attempts
    """

    # 连接事务由调用者管理, 队列操作可与其他本地写入共同提交。
    def __init__(self, connection) -> None:
        self._connection = connection

    # 入队先验证队列名和可选去重键, 重复键不生成第二条记录。
    def enqueue(
        self, queue: str, payload: dict[str, Any], *, dedup_key: str | None = None
    ) -> None:
        if not isinstance(queue, str) or not queue:
            raise QueueError("INVALID_QUEUE_NAME")
        if dedup_key is not None and (
            not isinstance(dedup_key, str) or not dedup_key
        ):
            raise QueueError("INVALID_DEDUP_KEY")
        # 载荷按 JSON 保存, 去重由数据库唯一约束处理并发。
        self._connection.execute(
            "INSERT INTO queue_items (queue, payload, dedup_key) "
            "VALUES (%s, %s::jsonb, %s) "
            "ON CONFLICT (dedup_key) DO NOTHING",
            (
                queue,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                dedup_key,
            ),
        )

    # 批量领取必须有正数量和租约时长, 领取会递增尝试次数。
    def claim(
        self, queue: str, limit: int = 10, lease_seconds: int = 120
    ) -> list[QueueItem]:
        if not isinstance(queue, str) or not queue:
            raise QueueError("INVALID_QUEUE_NAME")
        if limit < 1 or lease_seconds < 1:
            raise QueueError("INVALID_CLAIM_ARGUMENTS")
        # 一条语句同时选择并标记领取, 避免消费者拿到同一可用行。
        result = self._connection.execute(
            self._CLAIM_SQL, (queue, limit, lease_seconds)
        )
        # 把驱动行转换为不可变队列项, 保留实际领取次数。
        return [
            QueueItem(
                item_id=row[0],
                queue=row[1],
                payload=row[2] if isinstance(row[2], dict) else {},
                attempts=row[3],
            )
            for row in result.fetchall()
        ]

    # 只将已领取条目改为完成, 已结束条目不会再次修改状态。
    def complete(self, item_id: int) -> None:
        self._connection.execute(
            "UPDATE queue_items SET state = 'done', claimed_until = NULL "
            "WHERE id = %s AND state = 'claimed'",
            (item_id,),
        )

    # 续租仅影响已领取条目, 延长等待不改变业务执行结果。
    def extend(self, item_id: int, lease_seconds: int) -> None:
        if lease_seconds < 1:
            raise QueueError("INVALID_CLAIM_ARGUMENTS")
        self._connection.execute(
            "UPDATE queue_items "
            "SET claimed_until = now() + make_interval(secs => %s) "
            "WHERE id = %s AND state = 'claimed'",
            (lease_seconds, item_id),
        )

    # 失败重入是显式消费决定; 调用方必须先判断业务是否允许重试。
    def requeue_failed(self, item_id: int) -> None:
        self._connection.execute(
            "UPDATE queue_items SET state = 'pending', claimed_until = NULL "
            "WHERE id = %s AND state = 'claimed'",
            (item_id,),
        )
