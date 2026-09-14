import json
import os
from pathlib import Path
import tempfile
import unittest

import httpx

from deploy.mvp.runtime_support import (
    ModelRequestBudgetGuard, RequestBudget, SafeErrorObserver,
)


def request(max_tokens=128):
    return httpx.Request(
        "POST", "https://api.deepseek.com/chat/completions",
        json={"model": "deepseek-v4-flash", "max_tokens": max_tokens, "stream": False},
    )


class RuntimeSupportTest(unittest.TestCase):
    def test_budget_is_persisted_and_reloaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            RequestBudget(path, 2, 128).admit(request(), request().read())
            RequestBudget(path, 2, 128).admit(request(), request().read())
            self.assertEqual({"schemaVersion": 1, "limit": 2, "calls": 2},
                             json.loads(path.read_text()))
            with self.assertRaisesRegex(ModelRequestBudgetGuard, "MODEL_CALL_LIMIT_EXCEEDED"):
                RequestBudget(path, 2, 128).admit(request(), request().read())

    def test_budget_rejects_configuration_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            RequestBudget(path, 2, 128).admit(request(), request().read())
            with self.assertRaisesRegex(ModelRequestBudgetGuard, "MODEL_BUDGET_STATE_INVALID"):
                RequestBudget(path, 3, 128).admit(request(), request().read())

    def test_existing_empty_or_corrupt_budget_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            for raw in ("", "{not-json"):
                path.write_text(raw)
                with self.assertRaisesRegex(
                        ModelRequestBudgetGuard, "MODEL_BUDGET_STATE_INVALID"):
                    RequestBudget(path, 2, 128).admit(request(), request().read())
                self.assertEqual(raw, path.read_text())

    def test_safe_observer_does_not_persist_untrusted_message(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "errors.jsonl"
            previous = os.environ.get("A2FLOW_SAFE_ERROR_FILE")
            os.environ["A2FLOW_SAFE_ERROR_FILE"] = str(path)
            try:
                try:
                    raise RuntimeError("secret-value must not be logged")
                except RuntimeError as error:
                    SafeErrorObserver()(error)
            finally:
                if previous is None:
                    os.environ.pop("A2FLOW_SAFE_ERROR_FILE", None)
                else:
                    os.environ["A2FLOW_SAFE_ERROR_FILE"] = previous
            record = json.loads(path.read_text())
            self.assertEqual("RuntimeError", record["exceptionType"])
            self.assertIsNone(record["code"])
            self.assertNotIn("secret-value", path.read_text())

    def test_safe_observer_does_not_treat_uppercase_text_as_allowlisted_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "errors.jsonl"
            previous = os.environ.get("A2FLOW_SAFE_ERROR_FILE")
            os.environ["A2FLOW_SAFE_ERROR_FILE"] = str(path)
            try:
                try:
                    raise RuntimeError("PRIVATE_CUSTOMER_TOKEN")
                except RuntimeError as error:
                    SafeErrorObserver()(error)
            finally:
                if previous is None:
                    os.environ.pop("A2FLOW_SAFE_ERROR_FILE", None)
                else:
                    os.environ["A2FLOW_SAFE_ERROR_FILE"] = previous
            record = json.loads(path.read_text())
            self.assertIsNone(record["code"])
            self.assertNotIn("PRIVATE_CUSTOMER_TOKEN", path.read_text())


if __name__ == "__main__":
    unittest.main()
