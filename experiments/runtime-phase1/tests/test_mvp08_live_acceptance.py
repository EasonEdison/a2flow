"""Opt-in MVP08 live acceptance plus offline provider-budget checks."""

import json
import os
import unittest

import httpx

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
