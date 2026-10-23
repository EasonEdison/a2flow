#!/usr/bin/env python3
"""Exercise commit-triggered Chat dispatch in an isolated PostgreSQL database."""

from __future__ import annotations

import importlib
import json
import os
import sys
import unittest
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).absolute().parents[1]


def main():
    dsn = os.environ["A2FLOW_PROBE_DATABASE_URL"]
    if conninfo_to_dict(dsn).get("dbname") != "a2flow_chat_wake_probe_ci":
        raise ValueError("DISPOSABLE_CHAT_WAKE_DATABASE_REQUIRED")
    os.environ["A2FLOW_WAKE_PROBE_DSN"] = dsn
    sys.path.insert(0, str(ROOT / "services/b-side-api/tests"))
    module = importlib.import_module("test_chat_dispatch_wake_postgres")
    signal_suite = unittest.defaultTestLoader.loadTestsFromName("test_chat_wake.ChatWakeTests")
    postgres_suite = unittest.defaultTestLoader.loadTestsFromName(
        "test_chat_dispatch_wake_postgres.ChatDispatchWakeTests"
    )
    signal_checks, postgres_checks = signal_suite.countTestCases(), postgres_suite.countTestCases()
    suite = unittest.TestSuite([signal_suite, postgres_suite])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    with psycopg.connect(dsn) as c:
        cleaned = (
            c.execute(
                "SELECT count(*) FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname NOT LIKE 'pg_%'"
            ).fetchone()[0]
            == 0
        )
    passed = (
        result.wasSuccessful()
        and signal_checks >= 12
        and postgres_checks >= 23
        and result.testsRun >= 35
        and not result.skipped
        and cleaned
    )
    print(
        json.dumps(
            {
                "probe": "chat-dispatch-wake",
                "result": "PASS" if passed else "FAIL",
                "checks": result.testsRun,
                "signalChecks": signal_checks,
                "postgresChecks": postgres_checks,
                "postgres": True,
                "probeResourcesRemoved": cleaned,
                "externalModelCalls": 0,
                "externalBusinessCalls": 0,
                "scriptedNativePort": True,
                "measurements": module.METRICS,
                "acceleratedScenarios": {
                    "reconcileSeconds": [0.08, 0.1, 0.12],
                    "retrySeconds": [0.06, 0.12],
                    "busyRetrySeconds": 2.0,
                },
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
