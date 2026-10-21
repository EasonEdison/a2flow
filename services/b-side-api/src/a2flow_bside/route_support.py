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
    # 同步生成器在工作线程中读取, 通过队列桥接到异步 SSE。
    pending: queue.Queue[tuple[str, str | Exception | None]] = queue.Queue()

    # 生产者分别传递数据、结束和错误, 消费者不把异常误当正常完成。
    def produce() -> None:
        try:
            for chunk in sync_iter:
                pending.put(("chunk", chunk))
            pending.put(("done", None))
        except Exception as exc:
            pending.put(("error", exc))

    # 后台线程承担阻塞迭代, HTTP 事件循环只等待队列结果。
    threading.Thread(target=produce, daemon=True).start()

    # 消费者逐项取出数据; 错误沿异常路径传播, 不生成虚假的成功标记。
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


# 递归转换时间字段, 保持嵌套对象和列表结构不变。
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
    # 引用去掉完整 outputs, 仅保留受限结果页和来源元数据。
    frozen = {key: value for key, value in snapshot.items() if key != "outputs"}
    page = frozen["resultPage"]

    # 按最终 UTF-8 JSON 字节数计量, 转义字符和元数据都计入大小。
    def encoded_size(value: JsonObject) -> int:
        try:
            return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        except (TypeError, ValueError) as error:
            raise BsideError("INVALID_RUN_REFERENCE_RESULT", 502) from error

    # 未超过预算时保持原始结果页, 避免不必要截断。
    if encoded_size(frozen) <= 11000:
        return frozen

    # 截断时保留下一偏移, 允许用户继续读取后续结果。
    def shortened(length: int) -> JsonObject:
        return {
            **frozen,
            "resultPage": page[:length],
            "truncated": True,
            "nextOffset": frozen.get("resultOffset", 0) + length,
        }

    # 元数据本身超限直接报错, 不能仅删正文掩盖非法大引用。
    if encoded_size(shortened(0)) > 11000:
        raise BsideError("RUN_REFERENCE_METADATA_TOO_LARGE", 413)
    # 二分寻找字节预算内最长前缀, 避免按字符估算造成超限。
    low, high = 0, len(page)
    while low < high:
        middle = (low + high + 1) // 2
        if encoded_size(shortened(middle)) <= 11000:
            low = middle
        else:
            high = middle - 1
    return shortened(low)


# 将数据库下划线字段映射为前端协议, 并规范化时间值。
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
        # 下次、上次和创建时间分别展示, 不能用同一个时间代替运行事实。
        "nextRunAt": _iso(row["next_run_at"]),
        "lastRunAt": _iso(row["last_run_at"]),
        "createdAt": _iso(row["created_at"]),
    }
