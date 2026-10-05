"""Read-only projection of durable Chat messages with current card snapshots."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _identifier(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _turn_id(content: dict[str, Any]) -> str | None:
    execution = content.get("execution")
    if not isinstance(execution, dict):
        return None
    return _identifier(execution.get("turnId"))


def _event_card_id(event: dict[str, Any]) -> str | None:
    card_id = _identifier(event.get("cardId"))
    if card_id is not None:
        return card_id
    card = event.get("card")
    return _identifier(card.get("cardId")) if isinstance(card, dict) else None


def _matching_card(
    cards: dict[str, dict[str, Any]], card_id: str, turn_id: str | None,
) -> dict[str, Any] | None:
    card = cards.get(card_id)
    if card is None or turn_id is None or card.get("turnId") != turn_id:
        return None
    return deepcopy(card)


def has_card_references(rows: list[dict[str, Any]]) -> bool:
    """Return whether persisted messages explicitly reference a Chat card."""

    for row in rows:
        content = row.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if isinstance(parts, list) and any(
            isinstance(part, dict)
            and part.get("type") == "application"
            and _identifier(part.get("cardId")) is not None
            for part in parts
        ):
            return True
        events = content.get("events")
        if isinstance(events, list) and any(
            isinstance(event, dict)
            and event.get("type") == "application_rendered"
            and _event_card_id(event) is not None
            for event in events
        ):
            return True
    return False


def hydrate_history(
    rows: list[dict[str, Any]], cards: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Attach owner-scoped current cards without mutating messages or card rows."""

    projected = deepcopy(rows)
    card_by_id = {
        card_id: card
        for card in cards
        if isinstance(card, dict)
        and (card_id := _identifier(card.get("cardId"))) is not None
    }
    assigned: set[str] = set()
    for row in projected:
        if row.get("role") != "assistant":
            continue
        content = row.get("content")
        if not isinstance(content, dict):
            continue
        turn_id = _turn_id(content)
        parts = content.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict) or part.get("type") != "application":
                    continue
                card_id = _identifier(part.get("cardId"))
                if card_id is None:
                    continue
                card = _matching_card(card_by_id, card_id, turn_id)
                part["card"] = card
                if card is not None:
                    assigned.add(card_id)
            continue

        event_card_ids: set[str] = set()
        events = content.get("events")
        if isinstance(events, list):
            for event in events:
                if (
                    isinstance(event, dict)
                    and event.get("type") == "application_rendered"
                    and (card_id := _event_card_id(event)) is not None
                ):
                    event_turn_id = _identifier(event.get("turnId")) or turn_id
                    if _matching_card(card_by_id, card_id, event_turn_id) is not None:
                        event_card_ids.add(card_id)

        legacy_cards = []
        for card_id, card in card_by_id.items():
            if (
                card_id in assigned
                or (
                    card_id not in event_card_ids
                    and (turn_id is None or card.get("turnId") != turn_id)
                )
            ):
                continue
            legacy_cards.append(deepcopy(card))
            assigned.add(card_id)
        if legacy_cards:
            # Exact interleaving was not stored. The response preserves known
            # turn ownership, and clients render these after the legacy text.
            content["legacyCards"] = legacy_cards

    return projected, [
        deepcopy(card) for card_id, card in card_by_id.items()
        if card_id not in assigned
    ]
