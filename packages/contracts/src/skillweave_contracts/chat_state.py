"""Neutral state vocabulary; waiting for an action ends a turn, not a business task."""

from enum import StrEnum
from typing import Literal


class TurnSource(StrEnum):
    USER_MESSAGE = "USER_MESSAGE"
    PROCESSING = "PROCESSING"
    CARD_CONTINUATION = "CARD_CONTINUATION"


class ProductTurnStatus(StrEnum):
    """Product dispatch/delivery facts in chat_turns.status, never business success."""

    # 已接收并持久化, 等待分发; 不表示 Agent 已开始。
    QUEUED = "QUEUED"
    # 已进入产品分发/恢复检查, 不能据此判断原生执行者是否仍活跃。
    RUNNING = "RUNNING"
    # 本轮展示终态已提交, 包含 waiting_action; 不是整个业务任务完成。
    COMPLETED = "COMPLETED"
    # 执行事实未知或不一致, 阻止自动推进。
    NEEDS_REVIEW = "NEEDS_REVIEW"


class AgentTurnState(StrEnum):
    """Native execution evidence in agent_chat_turns.state, owned by the runner."""

    # 模型/工具调用前已记录准入; 该行可能在崩溃后残留, 不证明执行者存活。
    RUNNING = "RUNNING"
    # 已验证并保存完整结果, 可恢复展示而不重跑本轮。
    COMPLETED = "COMPLETED"
    # 原生执行异常或中断已记录, 不能据此断定外部业务操作失败。
    NEEDS_REVIEW = "NEEDS_REVIEW"


class TurnInspectionStatus(StrEnum):
    """Computed inspect_turn conclusion, not a column or another persisted state machine."""

    # 无本轮执行证据且无会话/checkpoint 阻断, 才允许新执行。
    NOT_STARTED = "NOT_STARTED"
    # 本次拿不到原生执行锁; 不是查到了某行 RUNNING。
    BUSY = "BUSY"
    # 本轮已保存的结果通过校验, 可修复产品投影而不调用模型或业务工具。
    COMPLETED = "COMPLETED"
    # 孤留执行、损坏结果或 checkpoint 事实不一致, 禁止自动重放。
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
