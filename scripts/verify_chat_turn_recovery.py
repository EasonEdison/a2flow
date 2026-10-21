#!/usr/bin/env python3
"""Exercise native Chat completion/crash facts only in a disposable database."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).absolute().parents[1]


def main():
    raw = os.environ["A2FLOW_PROBE_DATABASE_URL"]
    config = conninfo_to_dict(raw)
    if config.get("dbname") != "a2flow_chat_turn_probe_ci":
        raise ValueError("Disposable Chat probe database required")
    schema = "chat_turn_probe_" + uuid4().hex
    report = {"result": "FAIL", "probe": "chat-turn-recovery", "postgres": True,
              "probeResourcesRemoved": False, "checks": 0}
    with psycopg.connect(raw, autocommit=True) as c:
        c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        os.environ["A2FLOW_TEST_CHAT_DSN"] = make_conninfo(raw, options="-c search_path=" + schema + ",public")
        sys.path.insert(0, str(ROOT / "services/agent-workflow-runtime/tests"))
        suite = unittest.defaultTestLoader.loadTestsFromName("test_chat_recovery_postgres.DurableChatRecoveryTests")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        report["checks"] = result.testsRun
        report["result"] = "PASS" if result.wasSuccessful() and result.testsRun >= 4 and not result.skipped else "FAIL"
    finally:
        with psycopg.connect(raw, autocommit=True) as c:
            c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        report["probeResourcesRemoved"] = True
    print(json.dumps(report, sort_keys=True))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
