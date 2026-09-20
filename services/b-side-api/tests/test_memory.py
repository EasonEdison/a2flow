import asyncio
import unittest

from test_app import Harness, ORIGIN_HEADERS


class MemoryApiTests(unittest.TestCase):
    def test_authenticated_settings_and_identity_rejection(self):
        asyncio.run(self.flow())

    async def flow(self):
        calls = []
        def view(user):
            calls.append(("view", user))
            return {"revision": 0, "enabled": False, "entries": []}
        def replace(user, settings):
            calls.append(("replace", user, settings))
            return {**settings, "revision": settings["revision"] + 1}
        harness = Harness(memory_view=view, memory_replace=replace)
        async with await harness.client() as client:
            self.assertEqual(401, (await client.get("/api/memory")).status_code)
            registration = await client.post("/api/auth/register", headers=ORIGIN_HEADERS,
                json={"username": "memory-user", "password": "password-memory"})
            user = int(registration.json()["userId"])
            response = await client.get("/api/memory")
            self.assertEqual(200, response.status_code)
            settings = {"revision": 0, "enabled": True,
                        "entries": [{"id": "tone", "text": "concise"}]}
            self.assertNotEqual(200, (await client.put("/api/memory", json=settings)).status_code)
            response = await client.put("/api/memory", json=settings, headers=ORIGIN_HEADERS)
            self.assertEqual(200, response.status_code)
            self.assertEqual(1, response.json()["revision"])
            self.assertEqual(("replace", user, settings), calls[-1])
            before = len(calls)
            response = await client.put("/api/memory",
                json={**settings, "userId": "other"}, headers=ORIGIN_HEADERS)
            self.assertNotEqual(200, response.status_code)
            response = await client.get("/api/memory", headers={"X-User-Id": "other"})
            self.assertNotEqual(200, response.status_code)
            self.assertEqual(before, len(calls))
