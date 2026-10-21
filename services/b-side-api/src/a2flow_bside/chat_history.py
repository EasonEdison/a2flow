"""Read-only projection of durable Chat messages with current card snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any


# 历史关联只使用非空字符串身份, 不从文本中提取猜测标识。
def _identifier(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


# 从已保存执行投影读取轮次, 缺失时保留未知而不拿消息序号猜测。
def _turn_id(content: dict[str, Any]) -> str | None:
    execution = content.get("execution")
    if not isinstance(execution, dict):
        return None
    return _identifier(execution.get("turnId"))


# 兼容顶层卡片 ID 和旧嵌套卡片结构, 但仍要求显式引用。
def _event_card_id(event: dict[str, Any]) -> str | None:
    card_id = _identifier(event.get("cardId"))
    if card_id is not None:
        return card_id
    card = event.get("card")
    return _identifier(card.get("cardId")) if isinstance(card, dict) else None


# 卡片身份和轮次必须同时匹配, 防止同会话旧卡片被挂到错误回复。
def _matching_card(
    cards: dict[str, dict[str, Any]],
    card_id: str,
    turn_id: str | None,
) -> dict[str, Any] | None:
    card = cards.get(card_id)
    # 无法证明轮次归属时不嵌入卡片, 保留给未分配列表处理。
    if card is None or turn_id is None or card.get("turnId") != turn_id:
        return None
    return deepcopy(card)


# 检测历史是否确实引用卡片, 供路由判断卡片服务缺失是否影响恢复。
def has_card_references(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Return whether persisted messages explicitly reference a Chat card."""

    for row in rows:
        content = row.get("content")
        if not isinstance(content, dict):
            continue
        # 优先检查结构化内容片段, 不能仅因文本出现卡片字样就认作引用。
        parts = content.get("parts")
        if isinstance(parts, list) and any(
            isinstance(part, dict)
            and part.get("type") == "application"
            and _identifier(part.get("cardId")) is not None
            for part in parts
        ):
            return True
        # 兼容仅保存展示事件的旧消息, 同样依赖明确卡片标识。
        events = content.get("events")
        if isinstance(events, list) and any(
            isinstance(event, dict)
            and event.get("type") == "application_rendered"
            and _event_card_id(event) is not None
            for event in events
        ):
            return True
    return False


# 历史恢复只生成展示副本, 不修改消息表, 也不重新执行卡片动作。
def hydrate_history(
    rows: Sequence[Mapping[str, Any]],
    cards: list[dict[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]]]:
    """Attach owner-scoped current cards without mutating messages or card rows."""

    # 输入消息与卡片全部保持原样, 关联结果写到独立响应对象。
    projected = deepcopy(list(rows))
    card_by_id = {
        card_id: card
        for card in cards
        if isinstance(card, dict) and (card_id := _identifier(card.get("cardId"))) is not None
    }
    # 跟踪已匹配卡片, 使未归属产物可单独返回而不是静默丢弃。
    assigned: set[str] = set()
    for row in projected:
        # 仅助手消息承载卡片展示, 用户提交记录不被改写为卡片回复。
        if row.get("role") != "assistant":
            continue
        content = row.get("content")
        if not isinstance(content, dict):
            continue
        # 新版优先沿用保存的片段顺序, 准确恢复文字与卡片的交错位置。
        turn_id = _turn_id(content)
        parts = content.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict) or part.get("type") != "application":
                    continue
                # 每个应用片段核对显式卡片引用, 并与消息轮次交叉检查。
                card_id = _identifier(part.get("cardId"))
                if card_id is None:
                    continue
                card = _matching_card(card_by_id, card_id, turn_id)
                # 只补入当前权威卡片快照, 已提交状态不被旧历史快照覆盖。
                part["card"] = card
                if card is not None:
                    assigned.add(card_id)
            continue

        # 旧消息没有片段时, 先收集可证实属于本轮的展示事件。
        event_card_ids: set[str] = set()
        events = content.get("events")
        if isinstance(events, list):
            for event in events:
                if (
                    isinstance(event, dict)
                    and event.get("type") == "application_rendered"
                    and (card_id := _event_card_id(event)) is not None
                ):
                    # 事件自带轮次优先, 否则使用消息中已保存的轮次, 仍不猜测。
                    event_turn_id = _identifier(event.get("turnId")) or turn_id
                    if _matching_card(card_by_id, card_id, event_turn_id) is not None:
                        event_card_ids.add(card_id)

        # 旧格式无法还原精确交错位置, 只把已知归属卡片放在旧正文之后。
        legacy_cards = []
        for card_id, card in card_by_id.items():
            if card_id in assigned or (
                card_id not in event_card_ids and (turn_id is None or card.get("turnId") != turn_id)
            ):
                continue
            # 同一卡片只分配一次, 多个旧引用不会生成重复卡片。
            legacy_cards.append(deepcopy(card))
            assigned.add(card_id)
        if legacy_cards:
            # Exact interleaving was not stored. The response preserves known
            # turn ownership, and clients render these after the legacy text.
            content["legacyCards"] = legacy_cards

    # 未分配卡片单独返回, 避免坏历史关系导致已创建产物彻底不可见。
    return projected, [
        deepcopy(card) for card_id, card in card_by_id.items() if card_id not in assigned
    ]
