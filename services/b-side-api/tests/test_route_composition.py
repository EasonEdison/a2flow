"""Refactor contract checks: real assembly, offline external boundaries.

The fixture was captured from b5785c5 before splitting the route factory. It pins
public routing order and OpenAPI wire contracts, independent of Python modules.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.routing import APIRoute
from test_app import ORIGIN_HEADERS
from test_chat_lifespan import CurrentHarness as Harness

FIXTURE = Path(__file__).with_name("fixtures") / "routes-b5785c5.json"


def registered_routes(router):
    """FastAPI 0.141 retains included routers rather than flattening app.routes."""
    for route in router.routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from registered_routes(route.original_router)


def contract(app):
    """Hash each complete schema instead of storing generated documentation noise."""
    schema = app.openapi()

    def digest(value: object) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    return {
        "routes": [
            {
                "path": route.path,
                "methods": sorted(route.methods),
                "status": route.status_code,
                "responseClass": route.response_class.__name__
                if isinstance(route.response_class, type)
                else str(type(route.response_class).__name__),
            }
            for route in registered_routes(app.router)
        ],
        "paths": {path: digest(spec) for path, spec in schema["paths"].items()},
        "schemas": {
            name: digest(spec)
            for name, spec in schema.get("components", {}).get("schemas", {}).items()
        },
    }


class RouteContractTests(unittest.TestCase):
    def test_public_routes_order_and_wire_schemas_match_pre_refactor(self):
        self.assertEqual(json.loads(FIXTURE.read_text()), contract(Harness().app))

    def test_auth_origin_query_and_ownership_rejections(self):
        async def check():
            harness = Harness()
            async with harness.app.router.lifespan_context(harness.app):
                async with await harness.client() as client:
                    client.cookies.clear()
                    cases = [
                        (
                            "GET",
                            "/api/conversations/messages?conversationId=123",
                            None,
                            {},
                            401,
                            "AUTHENTICATION_REQUIRED",
                        ),
                        ("POST", "/api/conversations", {}, {}, 403, "ORIGIN_REQUIRED"),
                        (
                            "GET",
                            "/api/conversations/messages?conversationId=123&extra=1",
                            None,
                            {},
                            400,
                            "QUERY_PARAMETERS_NOT_ALLOWED",
                        ),
                    ]
                    for method, path, body, headers, status, code in cases:
                        response = await client.request(method, path, json=body, headers=headers)
                        self.assertEqual(
                            (status, code), (response.status_code, response.json()["error"]["code"])
                        )
                    await client.post(
                        "/api/auth/register",
                        json={"username": "route-owner", "password": "route-password-1"},
                        headers=ORIGIN_HEADERS,
                    )
                    harness.components["conversations"].rows[123] = {"user_id": 999}
                    response = await client.get("/api/conversations/messages?conversationId=123")
                    self.assertEqual(
                        (404, "NOT_FOUND"), (response.status_code, response.json()["error"]["code"])
                    )

        asyncio.run(check())


class ProductionCompositionTests(unittest.TestCase):
    """Construct real factories; block network and replace only explicit I/O edges."""

    ENV = {
        "A2FLOW_BSIDE_DATABASE_URL": "host=127.0.0.1 dbname=composition_probe user=probe",
        "A2FLOW_BSIDE_DATABASE_NAME": "composition_probe",
        "A2FLOW_BSIDE_PEPPER": "composition-probe-only-pepper",
        "A2FLOW_BSIDE_ENVIRONMENT": "PRT",
        "A2FLOW_BSIDE_ASSET_NAMESPACE": "composition-probe",
        "A2FLOW_BSIDE_BROWSER_ORIGIN": "http://127.0.0.1:14177",
        "A2FLOW_BSIDE_RUNTIME_URL": "http://127.0.0.1:14176",
        "A2FLOW_BSIDE_SESSION_SECONDS": "7200",
        "A2FLOW_BSIDE_VALIDATOR_FACTORY": "deploy.assets:bundle_validator",
    }

    def assemble(self, module):
        from a2flow_asset_store.personal_workflows import PersonalWorkflowReader
        from a2flow_bside.account_guard import PostgresAccountGuard
        from a2flow_bside.app import create_app
        from a2flow_bside.durable_chat import DurableChat, DurableDispatcher
        from agent_workflow_runtime.chat.cards import ChatCardStore
        from agent_workflow_runtime.rpc_client import RpcClient

        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)
            factory = kwargs.get("chat_runtime_factory")
            if factory is not None:

                def runtime_factory(wake):
                    runtime = factory(wake)
                    captured["runtime"] = runtime
                    captured["wake"] = wake
                    return runtime

                kwargs["chat_runtime_factory"] = runtime_factory
            return create_app(**kwargs)

        async def hold_worker(worker, stop):
            captured["dispatcher"] = worker
            await stop.wait()

        with (
            patch.dict(os.environ, self.ENV, clear=True),
            patch.object(module, "_load_validator", return_value=object()),
            patch.object(module, "create_app", side_effect=capture),
            patch.object(PostgresAccountGuard, "check_ready") as ready,
            patch.object(RpcClient, "from_environment", return_value=object()),
            patch.object(PersonalWorkflowReader, "list_workflows", return_value=()),
            patch.object(DurableChat, "check_ready") as chat_ready,
            patch.object(DurableDispatcher, "run", hold_worker),
            patch.object(ChatCardStore, "list", autospec=True, return_value=[]) as cards,
            patch("psycopg.connect", side_effect=AssertionError("unexpected database access")),
            patch("socket.socket.connect", side_effect=AssertionError("unexpected network access")),
        ):
            app = module.create_app_from_environment()
            self.assertEqual([], captured["workflow_catalog"](7))
            ready.assert_called_once_with()
            self.assertNotIn("runtime", captured, "Chat must not be constructed before startup")

            async def check_startup():
                async with app.router.lifespan_context(app):
                    if captured.get("chat_runtime_factory") is not None:
                        runtime = captured["runtime"]
                        self.assertIs(runtime.durable_chat.wake, captured["wake"])
                        self.assertIs(captured["wake"], captured["dispatcher"].store.wake)
                        self.assertEqual([], runtime.cards(7, "synthetic-conversation"))
                        cards.assert_called_once()
                        card_store = (
                            cards.call_args.args[0] if len(cards.call_args.args) == 3 else None
                        )
                        if card_store is not None:
                            self.assertIs(
                                runtime.durable_chat, card_store._completion_observer.__self__
                            )
                        chat_ready.assert_called_once_with()
                    else:
                        chat_ready.assert_not_called()

            asyncio.run(check_startup())
        return app, captured

    def test_generic_environment_factory_constructs_real_dependencies(self):
        from a2flow_bside import assembly
        from a2flow_bside.repositories import MessagesRepository
        from a2flow_bside.runtime_client import HttpRuntimeClient

        app, dependencies = self.assemble(assembly)
        self.assertIsInstance(dependencies["messages"], MessagesRepository)
        self.assertIsInstance(dependencies["runtime_client"], HttpRuntimeClient)
        self.assertEqual(contract(Harness().app), contract(app))

    def test_attended_and_realchat_use_durable_runner_and_same_public_routes(self):
        from a2flow_bside.durable_chat import DurableChat
        from a2flow_bside.processing_tasks import ProcessingTasksRepository
        from deploy.attended import bside_app
        from deploy.attended.chat_runner import ChatLoopRunner
        from deploy.realchat import launcher

        app, dependencies = self.assemble(bside_app)
        self.assertIsInstance(dependencies["runtime"].runner, ChatLoopRunner)
        self.assertIsInstance(dependencies["runtime"].durable_chat, DurableChat)
        self.assertIsInstance(dependencies["processing_tasks"], ProcessingTasksRepository)
        self.assertEqual(contract(Harness().app), contract(app))
        with (
            tempfile.TemporaryDirectory() as static,
            patch.dict(os.environ, {"A2FLOW_EMPLOYEE_STATIC_DIRECTORY": static}),
            patch.object(bside_app, "create_app_from_environment", return_value=app) as factory,
        ):
            self.assertIs(app, launcher.bside())
            factory.assert_called_once_with()
        self.assertEqual("/employee", app.routes[-1].path)


class RuntimeCompositionTests(unittest.TestCase):
    def test_realchat_constructs_native_host_without_external_calls(self):
        from agent_workflow_runtime.mvp_host import VerifiedIdentity
        from agent_workflow_runtime.rpc_client import RpcClient
        from deploy.realchat import launcher

        with (
            patch.dict(
                os.environ,
                {
                    "A2FLOW_DATABASE_URL": "host=127.0.0.1 dbname=composition_probe user=probe",
                    "A2FLOW_DATABASE_NAME": "composition_probe",
                    "A2FLOW_ASSET_NAMESPACE": "composition-probe",
                },
                clear=True,
            ),
            patch.object(RpcClient, "from_environment", return_value=object()),
            patch("psycopg.connect", side_effect=AssertionError("unexpected database access")),
            patch("socket.socket.connect", side_effect=AssertionError("unexpected network access")),
        ):
            wrapped = launcher.runtime()
        self.assertIsInstance(wrapped, VerifiedIdentity)
        expected = FIXTURE.with_name("runtime-routes-b5785c5.json")
        self.assertEqual(json.loads(expected.read_text()), contract(wrapped.app))


if __name__ == "__main__":
    unittest.main()
