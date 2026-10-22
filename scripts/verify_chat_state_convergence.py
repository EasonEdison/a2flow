#!/usr/bin/env python3
"""Run real PostgreSQL Chat state/transaction probes in a disposable DB."""

from __future__ import annotations

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
    if conninfo_to_dict(dsn).get("dbname") != "a2flow_chat_state_probe_ci":
        raise ValueError("DISPOSABLE_CHAT_STATE_DATABASE_REQUIRED")
    os.environ["A2FLOW_CONVERGENCE_DSN"] = dsn
    os.environ["A2FLOW_TEST_CHAT_DSN"] = dsn
    os.environ["A2FLOW_TEST_CHAT_CARDS_DSN"] = dsn
    sys.path.insert(0, str(ROOT / "examples/activity-planning"))
    sys.path.insert(0, str(ROOT / "services/b-side-api/tests"))
    sys.path.insert(0, str(ROOT / "services/agent-workflow-runtime/tests"))
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        [
            "test_chat_state_convergence_postgres.ChatStateConvergenceTests",
            "test_chat_result_postgres.ChatResultPersistenceTests",
            "test_chat_postgres.PostgresConversationTests",
            "test_chat_vertical.ChatVerticalTest",
            "test_chat_delivery_postgres.DeliveryPostgresTests",
            "test_work_activities_chat_state_postgres.WorkActivitiesChatStateTests",
        ]
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    with psycopg.connect(dsn) as connection:
        resources_removed = (
            connection.execute(
                "SELECT count(*) FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') "
                "AND nspname NOT LIKE 'pg_%'"
            ).fetchone()[0]
            == 0
        )
    passed = (
        result.wasSuccessful()
        and result.testsRun >= 25
        and not result.skipped
        and resources_removed
    )
    print(
        json.dumps(
            {
                "probe": "chat-state-convergence",
                "result": "PASS" if passed else "FAIL",
                "checks": result.testsRun,
                "postgres": True,
                "probeResourcesRemoved": resources_removed,
                "externalModelCalls": 0,
                "externalBusinessCalls": 0,
                "scriptedModels": True,
                "scope": "isolated PostgreSQL transactions, current schema, result recovery",
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
