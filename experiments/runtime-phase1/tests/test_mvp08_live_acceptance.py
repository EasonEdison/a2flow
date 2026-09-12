"""Opt-in MVP08 live acceptance plus offline provider-budget checks."""

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import httpx
from skillweave_contracts import TrustedContext

from runtime_phase1 import mvp08_live_probe as probe
from runtime_phase1.mvp08_live_probe import (
    MAX_OUTPUT_TOKENS_PER_CALL,
    MODEL_CALL_LIMIT, ModelRequestBudgetGuard, observe_backend_failure,
    RequestBudget,
    run,
)
from agent_workflow_runtime.mvp_host import create_mvp_app


def request(*, host="api.deepseek.com", tokens=MAX_OUTPUT_TOKENS_PER_CALL):
    return httpx.Request(
        "POST",
        f"https://{host}/chat/completions",
        content=json.dumps({
            "model": "deepseek-v4-flash",
            "max_tokens": tokens,
            "stream": False,
        }).encode(),
        headers={"content-type": "application/json"},
    )


class ModelBudgetTest(unittest.TestCase):
    def test_host_persists_bounded_backend_origin_but_keeps_public_500_generic(self):
        sentinel = "sensitive-backend-message-must-not-persist"

        class FailingService:
            def __init__(self):
                self.error = None

            def start(self, *args):
                raise self.error

        async def exercise(error):
            service = FailingService()
            service.error = error
            owner = TrustedContext("synthetic-user", "PRT")
            app = create_mvp_app(
                service, object(), lambda *args: {}, lambda scope: owner,
                unexpected_error_observer=observe_backend_failure,
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://runtime.test",
            ) as client:
                response = await client.post("/runtime/runs", json={
                    "controlRequestId": "synthetic", "definitionKey": "synthetic",
                    "inputs": {},
                })
            self.assertEqual(500, response.status_code)
            self.assertEqual({"error": {"code": "INTERNAL_ERROR"}}, response.json())
            self.assertNotIn(sentinel, response.text)

        cases = (
            (ModelRequestBudgetGuard(sentinel), "MODEL_REQUEST_BUDGET_GUARD"),
            (httpx.ConnectError(sentinel), "PROVIDER_OR_SDK_EXCEPTION"),
            (ValueError(sentinel), "BACKEND_EXCEPTION"),
        )
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory).resolve() / "evidence.jsonl"
            evidence.touch(mode=0o600)
            spec = replace(probe.SPEC, evidence_file=evidence)
            with patch.object(probe, "SPEC", spec):
                for error, _ in cases:
                    asyncio.run(exercise(error))
            records = [json.loads(line) for line in evidence.read_text().splitlines()]
        self.assertEqual([expected for _, expected in cases], [
            record["backendCategory"] for record in records
        ])
        self.assertEqual(["BACKEND_FAILURE"] * 3, [record["stage"] for record in records])
        for record in records:
            self.assertRegex(record["backendExceptionType"], r"^[A-Za-z0-9_.<>-]{1,96}$")
            self.assertTrue(record["backendStackFrames"])
            self.assertTrue(all(
                "/" not in frame and "\\\\" not in frame
                for frame in record["backendStackFrames"]
            ))
        self.assertNotIn(sentinel, json.dumps(records))

    def test_http_error_keeps_allowlisted_code_without_response_body(self):
        sensitive = "sensitive-provider-body-must-not-persist"
        response = httpx.Response(503, json={
            "error": {"code": "INTERNAL_ERROR", "detail": sensitive},
        })
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory).resolve() / "evidence.jsonl"
            evidence.touch(mode=0o600)
            spec = replace(probe.SPEC, evidence_file=evidence)

            def fail(progress):
                progress.update({
                    "stage": "START_REQUEST",
                    "operation": "START_RUN",
                    "budget": SimpleNamespace(calls=4),
                })
                probe.assert_status(response)

            with patch.object(probe, "SPEC", spec), \
                    patch.object(probe, "_execute", side_effect=fail), \
                    self.assertRaisesRegex(RuntimeError, "MVP08_LIVE_CHAIN_FAILED"):
                probe._run()
            record = json.loads(evidence.read_text())
        self.assertEqual({
            "schemaVersion": 1,
            "stage": "LIVE_RESULT",
            "outcome": "FAILED",
            "errorStage": "START_REQUEST",
            "errorType": "SafeHttpFailure",
            "modelCalls": 4,
            "operation": "START_RUN",
            "failureKind": "HTTP_STATUS",
            "failureSite": "assert_status",
            "httpStatus": 503,
            "responseJson": True,
            "errorCode": "INTERNAL_ERROR",
        }, record)
        self.assertNotIn(sensitive, json.dumps(record))

    def test_only_exact_provider_request_is_admitted(self):
        budget = RequestBudget()
        candidate = request()
        budget.admit(candidate, candidate.read())
        self.assertEqual(1, budget.calls)

        for candidate in (
            request(host="example.com"),
            request(tokens=MAX_OUTPUT_TOKENS_PER_CALL + 1),
            httpx.Request("GET", "https://api.deepseek.com/chat/completions"),
        ):
            with self.assertRaises(RuntimeError):
                budget.admit(candidate, candidate.read())
        self.assertEqual(1, budget.calls)

    def test_seventh_model_request_is_rejected_before_dispatch(self):
        budget = RequestBudget()
        for _ in range(MODEL_CALL_LIMIT):
            candidate = request()
            budget.admit(candidate, candidate.read())
        candidate = request()
        with self.assertRaisesRegex(RuntimeError, "MODEL_CALL_LIMIT_EXCEEDED"):
            budget.admit(candidate, candidate.read())
        self.assertEqual(MODEL_CALL_LIMIT, budget.calls)


@unittest.skipUnless(
    os.environ.get("A2FLOW_MVP08_WINDOW_ID"),
    "requires one separately authorized MVP08 live window",
)
class LiveChainTest(unittest.TestCase):
    def test_pg_seed_flash_wait_confirm_copy(self):
        evidence = run()
        self.assertEqual("PASS", evidence["status"])
        self.assertLessEqual(evidence["modelCalls"], MODEL_CALL_LIMIT)


if __name__ == "__main__":
    unittest.main()
