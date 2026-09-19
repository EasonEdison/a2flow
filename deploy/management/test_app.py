"""Offline private-preview Host checks; no listener or PostgreSQL connection."""

import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from a2flow_asset_store import AssetReader, PostgresAssetRepository
from a2flow_management import PostgresDraftRepository
from activity_planning_demo import bundle_validator

from deploy.management.app import (
    ManagementPreviewConfig,
    create_app_from_environment,
    create_management_preview_host,
)


TOKEN = b"af11-private-preview-token-000000000001"
GUEST_TOKEN = b"af11-private-preview-guest-000000000001"
BROWSER_ORIGIN = "http://127.0.0.1:14176"


async def request(
        app, path, *, method="GET", token=None, headers=None, base_url=None,
        **kwargs):
    values = dict(headers or {})
    if token is not None:
        values["Authorization"] = "Bearer " + token
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
            transport=transport,
            base_url=base_url or "http://127.0.0.1") as client:
        return await client.request(method, path, headers=values, **kwargs)


class ManagementPreviewHostTests(unittest.TestCase):
    def setUp(self):
        self.config = ManagementPreviewConfig(
            conninfo="host=/private/socket dbname=a2flow",
            database="a2flow",
            environment="PRT",
            namespace="a2flow-mvp-activity-planning",
            user_id="preview-admin",
            roles=frozenset({"ADMIN"}),
        )
        self.host = create_management_preview_host(
            self.config, validator=bundle_validator(), bearer_token=TOKEN)

    def call(self, path, **kwargs):
        return asyncio.run(request(self.host.app, path, **kwargs))

    def browser_config(self, directory, *, roles=frozenset({"ADMIN"})):
        return ManagementPreviewConfig(
            conninfo=self.config.conninfo,
            database=self.config.database,
            environment=self.config.environment,
            namespace=self.config.namespace,
            user_id=self.config.user_id,
            roles=roles,
            static_directory=directory,
            browser_origin=BROWSER_ORIGIN,
        )

    def test_factory_uses_real_postgres_adapters_without_connecting(self):
        self.assertIsInstance(self.host.reader, AssetReader)
        self.assertIsInstance(
            self.host.reader.repository, PostgresAssetRepository)
        self.assertIsInstance(self.host.drafts, PostgresDraftRepository)
        self.assertEqual("PRT", self.host.reader.repository.environment)
        self.assertEqual("a2flow", self.host.reader.repository.database)
        self.assertEqual("PRT", self.host.drafts.environment)
        self.assertEqual("a2flow", self.host.drafts.database)
        self.assertNotIn(self.config.conninfo, repr(self.config))

    def test_missing_and_wrong_authentication_fail_closed_as_json(self):
        for supplied in (None, "wrong-private-preview-token-000000000"):
            with self.subTest(supplied=supplied):
                response = self.call("/management/session", token=supplied)
                self.assertEqual(401, response.status_code)
                self.assertEqual(
                    "application/json", response.headers["content-type"])
                self.assertEqual(
                    "PREVIEW_AUTHENTICATION_REQUIRED",
                    response.json()["error"]["code"],
                )

    def test_authenticated_session_uses_only_server_principal(self):
        response = self.call(
            "/management/session", token=TOKEN.decode("ascii"))
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual({
            "userId": "preview-admin",
            "environment": "PRT",
            "registeredKinds": ["ABILITY", "APPLICATION", "SKILL", "WORKFLOW"],
            "canAuthor": True,
        }, response.json())

    def test_client_identity_headers_and_query_are_rejected(self):
        for header in ("X-User-Id", "X-Environment", "X-Role"):
            with self.subTest(header=header):
                response = self.call(
                    "/management/session",
                    token=TOKEN.decode("ascii"),
                    headers={header: "attacker"},
                )
                self.assertEqual(400, response.status_code)
                self.assertEqual(
                    "CLIENT_IDENTITY_FIELDS_NOT_ALLOWED",
                    response.json()["error"]["code"],
                )
        response = self.call(
            "/management/session?userId=attacker",
            token=TOKEN.decode("ascii"),
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual(
            "QUERY_PARAMETERS_NOT_ALLOWED", response.json()["error"]["code"])

    def test_non_loopback_server_is_rejected_even_with_valid_token(self):
        response = self.call(
            "/management/session",
            token=TOKEN.decode("ascii"),
            base_url="http://203.0.113.7",
        )
        self.assertEqual(403, response.status_code)
        self.assertEqual(
            "PRIVATE_PREVIEW_LOOPBACK_REQUIRED",
            response.json()["error"]["code"],
        )

    def test_browser_login_cookie_static_and_csrf_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text(
                "<h1>management-ui</h1>", encoding="utf-8")
            host = create_management_preview_host(
                self.browser_config(directory),
                validator=bundle_validator(),
                bearer_token=TOKEN,
            )

            async def scenario():
                transport = httpx.ASGITransport(
                    app=host.app, raise_app_exceptions=False)
                async with httpx.AsyncClient(
                        transport=transport,
                        base_url=BROWSER_ORIGIN,
                        follow_redirects=False) as client:
                    gated = await client.get("/")
                    self.assertEqual(303, gated.status_code)
                    self.assertEqual(
                        "/private-preview/login", gated.headers["location"])
                    api = await client.get("/management/session")
                    self.assertEqual(401, api.status_code)
                    self.assertEqual(
                        "application/json", api.headers["content-type"])
                    page = await client.get("/private-preview/login")
                    self.assertEqual(200, page.status_code)
                    self.assertEqual(
                        "same-origin", page.headers["referrer-policy"])
                    no_origin = await client.post(
                        "/private-preview/login",
                        data={"token": TOKEN.decode("ascii")},
                    )
                    self.assertEqual(401, no_origin.status_code)
                    wrong = await client.post(
                        "/private-preview/login",
                        data={"token": "wrong-private-preview-token-000000000"},
                        headers={"Origin": BROWSER_ORIGIN},
                    )
                    self.assertEqual(401, wrong.status_code)
                    self.assertNotIn(
                        "wrong-private-preview-token", wrong.text)
                    oversized = await client.post(
                        "/private-preview/login",
                        content=b"token=" + b"x" * 5000,
                        headers={
                            "content-type": "application/x-www-form-urlencoded",
                            "Origin": BROWSER_ORIGIN,
                        },
                    )
                    self.assertEqual(401, oversized.status_code)
                    login = await client.post(
                        "/private-preview/login",
                        data={"token": TOKEN.decode("ascii")},
                        headers={
                            "Origin": BROWSER_ORIGIN,
                            "Sec-Fetch-Site": "same-origin",
                        },
                    )
                    self.assertEqual(303, login.status_code)
                    cookie = login.headers["set-cookie"]
                    self.assertIn("HttpOnly", cookie)
                    self.assertIn("SameSite=strict", cookie)
                    self.assertIn("Max-Age=7200", cookie)
                    self.assertNotIn(TOKEN.decode("ascii"), cookie)
                    session = await client.get("/management/session")
                    self.assertEqual(200, session.status_code, session.text)
                    with patch(
                            "deploy.management.app.time.monotonic",
                            return_value=10**12):
                        expired = await client.get("/management/session")
                    self.assertEqual(401, expired.status_code)
                    static = await client.get("/")
                    self.assertEqual(200, static.status_code)
                    self.assertIn("management-ui", static.text)
                    csrf = await client.put(
                        "/management/assets/SKILL/demo%2Fskill/draft",
                        json={"expectedRevision": 0, "document": {}},
                    )
                    self.assertEqual(403, csrf.status_code)
                    self.assertEqual(
                        "PREVIEW_ORIGIN_REQUIRED",
                        csrf.json()["error"]["code"],
                    )

            asyncio.run(scenario())

    def test_cookie_user_session_cannot_author_even_with_valid_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text("ui", encoding="utf-8")
            host = create_management_preview_host(
                self.browser_config(directory, roles=frozenset({"USER"})),
                validator=bundle_validator(),
                bearer_token=TOKEN,
            )

            async def scenario():
                transport = httpx.ASGITransport(
                    app=host.app, raise_app_exceptions=False)
                async with httpx.AsyncClient(
                        transport=transport,
                        base_url=BROWSER_ORIGIN) as client:
                    login = await client.post(
                        "/private-preview/login",
                        data={"token": TOKEN.decode("ascii")},
                        headers={"Origin": BROWSER_ORIGIN},
                    )
                    self.assertEqual(303, login.status_code)
                    session = await client.get("/management/session")
                    self.assertFalse(session.json()["canAuthor"])
                    denied = await client.put(
                        "/management/assets/SKILL/demo%2Fskill/draft",
                        json={"expectedRevision": 0, "document": {}},
                        headers={"Origin": BROWSER_ORIGIN},
                    )
                    self.assertEqual(403, denied.status_code)
                    self.assertEqual(
                        "ADMIN_REQUIRED", denied.json()["error"]["code"])

            asyncio.run(scenario())

    def test_browser_login_and_static_reject_non_loopback_server(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text("ui", encoding="utf-8")
            host = create_management_preview_host(
                self.browser_config(directory),
                validator=bundle_validator(),
                bearer_token=TOKEN,
            )
            for path in ("/private-preview/login", "/"):
                with self.subTest(path=path):
                    response = asyncio.run(request(
                        host.app,
                        path,
                        base_url="http://203.0.113.7",
                    ))
                    self.assertEqual(403, response.status_code)
                    self.assertEqual(
                        "PRIVATE_PREVIEW_LOOPBACK_REQUIRED",
                        response.json()["error"]["code"],
                    )

    def test_environment_factory_requires_owner_only_regular_token_file(self):
        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / "management-token"
            token_path.write_bytes(TOKEN + b"\n")
            token_path.chmod(0o600)
            static_path = Path(directory) / "dist"
            static_path.mkdir()
            Path(static_path, "index.html").write_text("ui", encoding="utf-8")
            environment = {
                "A2FLOW_MANAGEMENT_DATABASE_URL": self.config.conninfo,
                "A2FLOW_MANAGEMENT_DATABASE_NAME": self.config.database,
                "A2FLOW_MANAGEMENT_ENVIRONMENT": self.config.environment,
                "A2FLOW_MANAGEMENT_ASSET_NAMESPACE": self.config.namespace,
                "A2FLOW_MANAGEMENT_USER_ID": self.config.user_id,
                "A2FLOW_MANAGEMENT_ROLES": "ADMIN",
                "A2FLOW_MANAGEMENT_VALIDATOR_FACTORY": (
                    "activity_planning_demo:bundle_validator"),
                "A2FLOW_MANAGEMENT_AUTH_TOKEN_FILE": str(token_path),
                "A2FLOW_MANAGEMENT_STATIC_DIRECTORY": str(static_path),
                "A2FLOW_MANAGEMENT_BROWSER_ORIGIN": BROWSER_ORIGIN,
            }
            with patch.dict(os.environ, environment, clear=False):
                app = create_app_from_environment()
                response = asyncio.run(request(
                    app,
                    "/management/session",
                    token=TOKEN.decode("ascii"),
                    base_url=BROWSER_ORIGIN,
                ))
                self.assertEqual(200, response.status_code, response.text)
                token_path.chmod(0o640)
                with self.assertRaisesRegex(
                        RuntimeError, "SECRET_FILE_PERMISSIONS"):
                    create_app_from_environment()
                token_path.chmod(0o600)
                link_path = Path(directory) / "management-token-link"
                link_path.symlink_to(token_path)
                environment["A2FLOW_MANAGEMENT_AUTH_TOKEN_FILE"] = str(link_path)
                with patch.dict(os.environ, environment, clear=False):
                    with self.assertRaisesRegex(
                            RuntimeError, "SECRET_FILE_UNAVAILABLE"):
                        create_app_from_environment()

    def test_browser_origin_accepts_loopback_and_explicit_public(self):
        accepted = {
            "http://127.0.0.1:14176": "http://127.0.0.1:14176",
            "http://127.0.0.1:14176/": "http://127.0.0.1:14176",
            "http://47.110.84.69": "http://47.110.84.69",
            "https://management.example.com": "https://management.example.com",
        }
        for origin, normalized in accepted.items():
            with self.subTest(origin=origin):
                with tempfile.TemporaryDirectory() as directory:
                    Path(directory, "index.html").write_text("ui", encoding="utf-8")
                    config = ManagementPreviewConfig(
                        conninfo=self.config.conninfo,
                        database=self.config.database,
                        environment=self.config.environment,
                        namespace=self.config.namespace,
                        user_id=self.config.user_id,
                        roles=self.config.roles,
                        static_directory=directory,
                        browser_origin=origin,
                    )
                    self.assertEqual(normalized, config.browser_origin)

    def test_browser_origin_rejects_path_and_userinfo(self):
        for origin in (
                "http://127.0.0.1:14176/path", "http://user:pass@127.0.0.1:14176"):
            with self.subTest(origin=origin):
                with tempfile.TemporaryDirectory() as directory:
                    Path(directory, "index.html").write_text("ui", encoding="utf-8")
                    with self.assertRaisesRegex(
                            RuntimeError, "INVALID_MANAGEMENT_BROWSER_ORIGIN"):
                        ManagementPreviewConfig(
                            conninfo=self.config.conninfo,
                            database=self.config.database,
                            environment=self.config.environment,
                            namespace=self.config.namespace,
                            user_id=self.config.user_id,
                            roles=self.config.roles,
                            static_directory=directory,
                            browser_origin=origin,
                        )


    def test_admin_and_guest_tokens_bind_distinct_principals(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text("ui", encoding="utf-8")
            config = ManagementPreviewConfig(
                conninfo=self.config.conninfo,
                database=self.config.database,
                environment=self.config.environment,
                namespace=self.config.namespace,
                user_id="preview-admin",
                roles=frozenset({"ADMIN"}),
                static_directory=directory,
                browser_origin=BROWSER_ORIGIN,
                guest_user_id="preview-guest",
            )
            host = create_management_preview_host(
                config, validator=bundle_validator(),
                bearer_token=TOKEN, guest_token=GUEST_TOKEN)

            async def run():
                transport = httpx.ASGITransport(
                    app=host.app, raise_app_exceptions=False)
                async with httpx.AsyncClient(
                        transport=transport, base_url=BROWSER_ORIGIN) as client:
                    guest = await client.post(
                        "/private-preview/login",
                        data={"token": GUEST_TOKEN.decode("ascii")},
                        headers={"Origin": BROWSER_ORIGIN},
                        follow_redirects=False,
                    )
                    self.assertEqual(303, guest.status_code)
                    session = await client.get("/management/session")
                    self.assertEqual(200, session.status_code)
                    payload = session.json()
                    self.assertEqual("preview-guest", payload["userId"])
                    self.assertFalse(payload["canAuthor"])
                    await client.post(
                        "/private-preview/logout",
                        headers={"Origin": BROWSER_ORIGIN},
                        follow_redirects=False,
                    )
                    admin = await client.post(
                        "/private-preview/login",
                        data={"token": TOKEN.decode("ascii")},
                        headers={"Origin": BROWSER_ORIGIN},
                        follow_redirects=False,
                    )
                    self.assertEqual(303, admin.status_code)
                    session = await client.get("/management/session")
                    self.assertEqual(200, session.status_code)
                    payload = session.json()
                    self.assertEqual("preview-admin", payload["userId"])
                    self.assertTrue(payload["canAuthor"])

            asyncio.run(run())

if __name__ == "__main__":
    unittest.main()
