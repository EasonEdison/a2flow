import asyncio
import unittest

from test_app import ORIGIN_HEADERS, Harness


class ChatHistoryApiTests(unittest.TestCase):
    def test_single_history_response_hydrates_latest_and_unassigned_cards(self):
        asyncio.run(self._flow())

    async def _flow(self):
        latest = {
            "cardId": "card-1", "turnId": "11", "status": "COMPLETED",
            "display": {"applicationKey": "people"},
        }
        orphan = {"cardId": "orphan", "status": "DISPLAY_ONLY"}
        calls = []
        harness = Harness(chat_cards=lambda user_id, conversation_id: (
            calls.append((user_id, conversation_id)) or [latest, orphan]
        ))
        async with await harness.client() as client:
            await client.post(
                "/api/auth/register", headers=ORIGIN_HEADERS,
                json={"username": "history-owner", "password": "password-valid"},
            )
            conversation = (await client.post(
                "/api/conversations", headers=ORIGIN_HEADERS, json={},
            )).json()["id"]
            stored_content = {
                "text": "回答",
                "execution": {"turnId": "11"},
                "parts": [{
                    "type": "application", "id": "application:card-1",
                    "cardId": "card-1",
                }],
            }
            harness.components["messages"].append(
                conversation_id=conversation, role="assistant",
                content=stored_content,
            )

            response = await client.get(
                f"/api/conversations/{conversation}/messages",
            )

            self.assertEqual(200, response.status_code)
            body = response.json()
            self.assertEqual("COMPLETED", body["messages"][0]["content"]
                             ["parts"][0]["card"]["status"])
            self.assertEqual([orphan], body["unassignedCards"])
            self.assertNotIn("card", stored_content["parts"][0])
            self.assertEqual([(1, str(conversation))], calls)

    def test_card_loader_failure_is_explicit(self):
        async def flow():
            def fail(_user_id, _conversation_id):
                raise RuntimeError("storage unavailable")

            harness = Harness(chat_cards=fail)
            async with await harness.client() as client:
                await client.post(
                    "/api/auth/register", headers=ORIGIN_HEADERS,
                    json={"username": "history-failure", "password": "password-valid"},
                )
                conversation = (await client.post(
                    "/api/conversations", headers=ORIGIN_HEADERS, json={},
                )).json()["id"]
                response = await client.get(
                    f"/api/conversations/{conversation}/messages",
                )
                self.assertEqual(503, response.status_code)
                self.assertEqual(
                    "CHAT_HISTORY_CARDS_UNAVAILABLE",
                    response.json()["error"]["code"],
                )

        asyncio.run(flow())


if __name__ == "__main__":
    unittest.main()
