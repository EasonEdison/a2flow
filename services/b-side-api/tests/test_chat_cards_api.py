import asyncio
import unittest

from test_app import Harness, ORIGIN_HEADERS


class ChatCardsApiTests(unittest.TestCase):
    def test_owner_csrf_and_closed_action_payload(self):
        asyncio.run(self.flow())

    async def flow(self):
        calls = []
        harness = Harness(
            chat_cards=lambda user, conversation: [{"cardId": "card-1"}],
            chat_action=lambda user, conversation, card, body: (
                calls.append((user, conversation, card, body)) or {"status": "COMPLETED"}),
        )
        async with await harness.client() as client:
            response = await client.post("/api/auth/register", headers=ORIGIN_HEADERS,
                json={"username": "card-owner", "password": "password-valid"})
            self.assertEqual(200, response.status_code)
            response = await client.post("/api/conversations", headers=ORIGIN_HEADERS, json={})
            conversation = response.json()["id"]
            path = f"/api/conversations/{conversation}/cards"
            self.assertEqual({"cards": [{"cardId": "card-1"}]}, (await client.get(path)).json())
            payload = {"requestId": "r-1", "actionName": "select", "inputs": {"optionId": "a"}}
            action_path = path + "/card-1/actions"
            self.assertEqual(403, (await client.post(action_path, json=payload)).status_code)
            forged = {**payload, "userId": "999"}
            self.assertEqual(400, (await client.post(action_path, headers=ORIGIN_HEADERS, json=forged)).status_code)
            stale_contract = {**payload, "expectedRevision": 0}
            self.assertEqual(400, (await client.post(
                action_path, headers=ORIGIN_HEADERS, json=stale_contract,
            )).status_code)
            self.assertEqual(200, (await client.post(action_path, headers=ORIGIN_HEADERS, json=payload)).status_code)
            self.assertEqual(1, calls[0][0])
            self.assertEqual(str(conversation), calls[0][1])
            await client.post("/api/auth/logout", headers=ORIGIN_HEADERS, json={})
            await client.post("/api/auth/register", headers=ORIGIN_HEADERS,
                json={"username": "other-owner", "password": "password-valid"})
            self.assertEqual(404, (await client.get(path)).status_code)
            self.assertEqual(404, (await client.post(action_path, headers=ORIGIN_HEADERS, json=payload)).status_code)
            self.assertEqual(1, len(calls))

    def test_unwired_cards_fail_closed(self):
        async def flow():
            harness = Harness()
            async with await harness.client() as client:
                await client.post("/api/auth/register", headers=ORIGIN_HEADERS,
                    json={"username": "card-owner", "password": "password-valid"})
                conversation = (await client.post("/api/conversations", headers=ORIGIN_HEADERS, json={})).json()["id"]
                self.assertEqual(503, (await client.get(f"/api/conversations/{conversation}/cards")).status_code)
        asyncio.run(flow())
