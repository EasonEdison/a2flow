"""Account ingress checks with independent sessions and real password hashing."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI
from a2flow_bside.auth import hash_password, hash_session_token, new_session_token
from deploy.accounts.app import AccountAuthentication, AccountError, create_app


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
                app = create_app(self.auth)
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as a, httpx.AsyncClient(transport=transport, base_url="http://test") as b:
                    self.assertEqual((await a.get("/")).status_code, 404)
                    page = await a.get("/login")
                    self.assertIn("A2Flow 登录", page.text)
                    self.assertNotIn("token", page.text)
                    for client, username in [(a, "admin"), (b, "reader")]:
                        reply = await client.post("/login", data={"username": username, "password": "test-password"}, headers={"origin": "http://test"})
                        self.assertEqual(reply.status_code, 303)
                        self.assertIn("HttpOnly", reply.headers["set-cookie"])
                    self.assertEqual((await a.get("/login")).headers["location"], "/")
                    self.assertEqual((await b.get("/login")).headers["location"], "/")
                    self.assertEqual((await a.get("/login", headers={"authorization": "Bearer legacy"})).status_code, 401)
                    self.assertEqual((await a.get("/", headers={"x-user-id": "999"})).status_code, 400)
                    self.assertEqual((await a.post("/logout", headers={"origin": "http://evil"})).status_code, 403)
                    self.assertEqual((await a.post("/private-preview/logout", headers={"origin": "http://test"})).status_code, 303)
                    self.assertEqual((await a.get("/login")).status_code, 200)
                    self.assertEqual((await b.get("/login")).status_code, 303)
                    for path in ("/", "/management/assets", "/api/management/v2/assets", "/docs", "/openapi.json"):
                        self.assertEqual((await b.get(path)).status_code, 404)
                        self.assertEqual((await b.post(path, headers={"origin": "http://test"})).status_code, 404)
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
        with self.assertRaises(AccountError):
            self.auth(scope)

    def test_shared_b_tokens_expiry_revocation_and_signed64(self):
        self.users.rows["admin"]["user_id"] = 9223372036854775807
        token = new_session_token()
        digest = hash_session_token(token)
        self.sessions.create(token_sha256=digest, user_id=9223372036854775807,
                             expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        scope = {"headers": [(b"cookie", ("a2flow_management_session=" + token).encode())]}
        self.assertEqual(self.auth(scope).user_id, 9223372036854775807)
        self.sessions.rows[digest]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        with self.assertRaises(AccountError):
            self.auth(scope)
        self.sessions.delete(digest)
        with self.assertRaises(AccountError):
            self.auth(scope)

    def test_browser_form_security_and_secure_cookie(self):
        async def run():
            auth = AccountAuthentication(users=self.users, sessions=self.sessions,
                pepper="test-pepper", environment="PRT", origins=["https://test"])
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(auth)),
                                          base_url="https://test") as client:
                headers = {"origin": "https://test", "content-type": "application/x-www-form-urlencoded"}
                for body in ("username=admin&username=admin&password=test-password",
                             "username=admin&password=test-password&extra=yes",
                             "username=admin&password=", "broken", "username=%FF&password=x"):
                    self.assertEqual((await client.post("/login", content=body, headers=headers)).status_code, 401)
                self.assertEqual((await client.post("/login", data={"username": "admin", "password": "test-password"})).status_code, 401)
                reply = await client.post("/login", data={"username": "admin", "password": "test-password"},
                    headers={"origin": "https://test", "sec-fetch-site": "cross-site"})
                self.assertEqual(reply.status_code, 401)
                reply = await client.post("/login", data={"username": "admin", "password": "test-password"}, headers=headers)
                self.assertEqual(reply.status_code, 303)
                for value in ("Secure", "HttpOnly", "SameSite=strict", "Max-Age=7200", "Path=/"):
                    self.assertIn(value, reply.headers["set-cookie"])
                self.assertEqual(reply.headers["location"], "/")
                reply = await client.post("/logout", headers={"origin": "https://test"})
                self.assertEqual(reply.status_code, 303)
                self.assertIn("Max-Age=0", reply.headers["set-cookie"])
        asyncio.run(run())
