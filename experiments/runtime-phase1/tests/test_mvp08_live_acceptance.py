"""Opt-in MVP08 live acceptance plus offline provider-budget checks."""

from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import httpx

from runtime_phase1 import mvp08_live_probe as probe
from runtime_phase1.mvp08_live_probe import (
    MAX_OUTPUT_TOKENS_PER_CALL,
    MODEL_CALL_LIMIT,
    RequestBudget,
    run,
)


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
