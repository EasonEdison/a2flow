import copy
import unittest

from a2flow_bside.chat_history import hydrate_history


class ChatHistoryTests(unittest.TestCase):
    def test_hydrates_new_parts_without_mutating_stored_messages(self):
        rows = [{
            "id": 12,
            "role": "assistant",
            "content": {
                "text": "最新回答",
                "execution": {"turnId": "11"},
                "parts": [
                    {"type": "text", "id": "text:12:1", "text": "开头"},
                    {"type": "application", "id": "application:card-1",
                     "cardId": "card-1"},
                    {"type": "application", "id": "application:missing",
                     "cardId": "missing"},
                ],
            },
        }]
        cards = [
            {"cardId": "card-1", "turnId": "11", "status": "COMPLETED"},
            {"cardId": "other-turn", "turnId": "99", "status": "WAITING_ACTION"},
        ]
        original_rows = copy.deepcopy(rows)
        original_cards = copy.deepcopy(cards)

        hydrated, unassigned = hydrate_history(rows, cards)

        self.assertEqual(original_rows, rows)
        self.assertEqual(original_cards, cards)
        self.assertEqual(
            "COMPLETED", hydrated[0]["content"]["parts"][1]["card"]["status"],
        )
        self.assertIsNone(hydrated[0]["content"]["parts"][2]["card"])
        self.assertEqual(["other-turn"], [card["cardId"] for card in unassigned])

    def test_legacy_cards_use_known_turn_without_inventing_parts(self):
        rows = [{
            "id": 12,
            "role": "assistant",
            "content": {
                "text": "旧回答",
                "execution": {"turnId": "11"},
                "events": [{
                    "type": "application_rendered", "turnId": "11",
                    "card": {"cardId": "card-2", "status": "STALE"},
                }],
            },
        }]
        cards = [
            {"cardId": "card-1", "turnId": "11", "status": "COMPLETED"},
            {"cardId": "card-2", "turnId": "11", "status": "WAITING_ACTION"},
            {"cardId": "orphan", "status": "DISPLAY_ONLY"},
        ]

        hydrated, unassigned = hydrate_history(rows, cards)

        content = hydrated[0]["content"]
        self.assertNotIn("parts", content)
        self.assertEqual(
            ["card-1", "card-2"],
            [card["cardId"] for card in content["legacyCards"]],
        )
        self.assertEqual("STALE", content["events"][0]["card"]["status"])
        self.assertEqual(["orphan"], [card["cardId"] for card in unassigned])


if __name__ == "__main__":
    unittest.main()
