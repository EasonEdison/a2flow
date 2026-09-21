"""Account ingress checks with independent sessions and real password hashing."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

import httpx
from fastapi import FastAPI
from a2flow_bside.auth import hash_password
from a2flow_management import ManagementError
from deploy.management.account_auth import AccountAuthentication, attach_account_browser


class Users:
    def __init__(self):
        self.rows = {name: {"user_id": uid, "role": role,
            "password_hash": hash_password("test-password", pepper="test-pepper")}
            for name, uid, role in [("admin", 101, "ADMIN"), ("reader", 202, "USER")]}

    def find_by_username(self, username):
        return self.rows.get(username)


class Sessions:
    def __init__(self, users):
        self.rows = {}
        self.users = users

    def create(self, **row):
        self.rows[row["token_sha256"]] = row

    def find_identity(self, digest, now):
        row = self.rows.get(digest)
        if row and row["expires_at"] > now:
            user = next(u for u in self.users.rows.values() if u["user_id"] == row["user_id"])
            return {"userId": user["user_id"], "role": user["role"]}

    def delete(self, digest):
        self.rows.pop(digest, None)


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.users = Users()
        self.sessions = Sessions(self.users)
        self.auth = AccountAuthentication(users=self.users, sessions=self.sessions,
            pepper="test-pepper", environment="PRT", origins=["http://test"])
        self.scope = {"headers": [(b"origin", b"http://test")], "method": "POST"}

    def test_concurrent_tokens_and_repository_restart(self):
        with ThreadPoolExecutor(2) as pool:
            tokens = list(pool.map(lambda name: self.auth.login(name, "test-password", self.scope), ["admin", "reader"]))
        self.assertEqual(len(set(tokens)), 2)
        restarted = AccountAuthentication(users=self.users, sessions=self.sessions,
            pepper="test-pepper", environment="PRT", origins=["http://test"])
        for token, uid in zip(tokens, [101, 202]):
            scope = {"headers": [(b"cookie", ("a2flow_management_session=" + token).encode())]}
            self.assertEqual(restarted(scope).user_id, uid)
        self.assertIsNone(self.auth.login("unknown", "test-password", self.scope))

    def test_browser_sessions_and_rejections(self):
        async def run():
            with tempfile.TemporaryDirectory() as directory:
                Path(directory, "index.html").write_text("management")
                app = FastAPI()
                attach_account_browser(app, self.auth, directory)
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as a, httpx.AsyncClient(transport=transport, base_url="http://test") as b:
                    self.assertEqual((await a.get("/")).headers["location"], "/login")
                    page = await a.get("/login")
                    self.assertIn("A2Flow 登录", page.text)
                    self.assertNotIn("token", page.text)
                    for client, username in [(a, "admin"), (b, "reader")]:
                        reply = await client.post("/login", data={"username": username, "password": "test-password"}, headers={"origin": "http://test"})
                        self.assertEqual(reply.status_code, 303)
                        self.assertIn("HttpOnly", reply.headers["set-cookie"])
                    self.assertEqual((await a.get("/")).status_code, 200)
                    self.assertEqual((await b.get("/")).status_code, 200)
                    self.assertEqual((await a.get("/", headers={"authorization": "Bearer legacy"})).status_code, 401)
                    self.assertEqual((await a.get("/", headers={"x-user-id": "999"})).status_code, 400)
                    self.assertEqual((await a.post("/logout", headers={"origin": "http://evil"})).status_code, 403)
                    self.assertEqual((await a.post("/private-preview/logout", headers={"origin": "http://test"})).status_code, 303)
                    self.assertEqual((await a.get("/")).status_code, 303)
                    self.assertEqual((await b.get("/")).status_code, 200)
                    bad = await a.post("/login", data={"token": "legacy"}, headers={"origin": "http://test"})
                    self.assertEqual(bad.status_code, 401)
                    oversized = await a.post("/login", content=b"password=" + b"a" * 5000, headers={"origin": "http://test", "content-type": "application/x-www-form-urlencoded"})
                    self.assertEqual(oversized.status_code, 401)
        asyncio.run(run())

    def test_role_changes_and_rate_limit(self):
        token = self.auth.login("admin", "test-password", self.scope)
        scope = {"headers": [(b"cookie", ("a2flow_management_session=" + token).encode())]}
        self.users.rows["admin"]["role"] = "USER"
        self.assertEqual(self.auth(scope).roles, frozenset({"USER"}))
        for _ in range(8):
            self.auth.login("admin", "wrong", self.scope)
        self.assertIsNone(self.auth.login("admin", "test-password", self.scope))
        self.users.rows["admin"]["role"] = "INVALID"
        with self.assertRaises(ManagementError):
            self.auth(scope)
