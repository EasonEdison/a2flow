#!/usr/bin/env python3
"""Real Python executor/PG admission probe; only an empty disposable local DB.

No model or business RPC is called. Reuses the capability executor's plan and
recording-transport fixtures; it does not run their unit-test functions.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import replace
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/capability-execution/src"))
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from a2flow.capability.v1 import capability_pb2 as pb
from a2flow_capability.approval import ApprovalGuard, PostgresApprovalStore, argument_bytes
from a2flow_capability.executor import CapabilityExecutor
from a2flow_capability.models import ExecutionErrorCode

spec = importlib.util.spec_from_file_location(
    "capability_executor_probe_fixtures",
    ROOT / "services/capability-execution/tests/test_executor.py",
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
ARGUMENTS = {"orderId": "synthetic-order"}
OWNER = replace(fixtures.context(), user_id=73)
CHECKS = 0


def check(condition: bool, message: str) -> None:
    global CHECKS
    if not condition:
        raise AssertionError(message)
    CHECKS += 1


def plan(side_effect: str = "WRITE", policy: str = "REQUEST_APPROVAL"):
    return replace(fixtures.plan(), side_effect_level=side_effect, approval_policy=policy)


def receipt(suffix: str, *, side_effect: str = "WRITE") -> pb.ApprovalReceipt:
    target = plan(side_effect)
    return pb.ApprovalReceipt(
        receipt_id=f"probe-{suffix}", confirmation_id=f"confirm-{suffix}",
        run_id="probe-run", tool_call_id=f"tool-{suffix}", user_id=OWNER.user_id,
        environment=pb.PRT, action_code=target.action_code, source_id=target.source_id,
        source_digest=target.source_digest, side_effect_level=side_effect,
        approval_policy=target.approval_policy,
        arguments_digest=hashlib.sha256(argument_bytes(ARGUMENTS)).hexdigest(),
    )


def copied(value: pb.ApprovalReceipt, **changes) -> pb.ApprovalReceipt:
    result = pb.ApprovalReceipt()
    result.CopyFrom(value)
    for name, new_value in changes.items():
        setattr(result, name, new_value)
    return result


def restart_attempt(arguments: tuple[str, str, bytes]) -> tuple[str, int]:
    dsn, database, raw = arguments
    value = pb.ApprovalReceipt.FromString(raw)
    transport = fixtures.RecordingTransport({"synthetic": True})
    executor = CapabilityExecutor(transport, ApprovalGuard(PostgresApprovalStore(dsn, database)))
    result = executor.execute(plan(), ARGUMENTS, OWNER, approval_receipt=value)
    return result.error_code.value if result.error_code else "", len(transport.calls)


def exercise(control, dsn: str, database: str, role: str) -> dict:
    store = PostgresApprovalStore(dsn, database)
    transport = fixtures.RecordingTransport({"synthetic": True})
    executor = CapabilityExecutor(transport, ApprovalGuard(store))

    def rejected(expected, target=None, value=None, arguments=None, raw=None):
        before = len(transport.calls)
        result = executor.execute(target or plan(), arguments or ARGUMENTS, OWNER,
                                  approval_receipt=value, arguments_json=raw)
        check(not result.success and result.error_code == expected, f"Expected {expected}")
        check(len(transport.calls) == before, "Rejected request dispatched transport")

    def rows() -> int:
        return control.execute("SELECT count(*) FROM capability_approval_consumption").fetchone()[0]

    with psycopg.connect(dsn) as connection:
        check(connection.execute("SHOW transaction_read_only").fetchone()[0] == "on",
              "Resolver role must remain read-only by default")
        for privilege in ("INSERT", "SELECT"):
            check(connection.execute("SELECT has_table_privilege(current_user,"
                                     "'capability_approval_consumption',%s)", (privilege,)).fetchone()[0],
                  "Missing minimal approval privilege")
        for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
            check(not connection.execute("SELECT has_table_privilege(current_user,"
                                         "'capability_approval_consumption',%s)", (privilege,)).fetchone()[0],
                  "Approval role has excess mutation privilege")

    for policy in ("AUTO_EXECUTE", "REQUEST_APPROVAL"):
        check(executor.execute(plan("READ", policy), ARGUMENTS, OWNER).success,
              "Compatible READ required confirmation")
    check(rows() == 0, "READ consumed a receipt")
    executor.prepare(plan(), ARGUMENTS, OWNER)
    check(rows() == 0 and len(transport.calls) == 2, "Preview consumed or dispatched")
    rejected(ExecutionErrorCode.APPROVAL_REQUIRED)
    for target in (plan("WRITE", "AUTO_EXECUTE"), plan("WRITE", "REQUEST"),
                   plan("UNKNOWN"), plan("", "")):
        rejected(ExecutionErrorCode.EXECUTION_PLAN_INVALID, target, receipt("invalid-plan"))
    valid = receipt("first")
    for changes in (
        {"user_id": 74}, {"environment": pb.ONLINE}, {"action_code": "other"},
        {"source_id": "other"}, {"source_digest": "other"},
        {"arguments_digest": "0" * 64}, {"side_effect_level": "READ"},
        {"approval_policy": "AUTO_EXECUTE"}, {"confirmation_id": ""},
        {"tool_call_id": ""}, {"run_id": ""}, {"receipt_id": "invalid space"},
    ):
        rejected(ExecutionErrorCode.APPROVAL_INVALID, value=copied(valid, **changes))
    missing_owner = copied(valid)
    missing_owner.ClearField("user_id")
    rejected(ExecutionErrorCode.APPROVAL_INVALID, value=missing_owner)
    rejected(ExecutionErrorCode.APPROVAL_INVALID, value=valid,
             arguments={"orderId": "other-order"})
    rejected(ExecutionErrorCode.APPROVAL_INVALID, value=valid,
             raw=b'{"orderId":"different-raw-data"}')
    check(rows() == 0, "Invalid admission persisted consumption")
    check(executor.execute(plan(), ARGUMENTS, OWNER, approval_receipt=valid).success,
          "Confirmed write did not execute")
    check(rows() == 1 and len(transport.calls) == 3, "First write did not consume once")
    rejected(ExecutionErrorCode.APPROVAL_ALREADY_CONSUMED, value=valid)
    rejected(ExecutionErrorCode.APPROVAL_ALREADY_CONSUMED,
             value=copied(valid, receipt_id="receipt-alias"))
    rejected(ExecutionErrorCode.APPROVAL_ALREADY_CONSUMED,
             value=copied(valid, receipt_id="second-alias", confirmation_id="second-confirmation"))

    concurrent = receipt("concurrent")
    def attempt(_):
        fresh = CapabilityExecutor(transport, ApprovalGuard(PostgresApprovalStore(dsn, database)))
        return fresh.execute(plan(), ARGUMENTS, OWNER, approval_receipt=concurrent)
    before = len(transport.calls)
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(attempt, range(8)))
    check(sum(outcome.success for outcome in outcomes) == 1, "Concurrent admission was not singular")
    check(sum(outcome.error_code == ExecutionErrorCode.APPROVAL_ALREADY_CONSUMED
              for outcome in outcomes) == 7, "Concurrent duplicates were not rejected")
    check(len(transport.calls) == before + 1, "Concurrent dispatch count changed")
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
        restored = pool.submit(restart_attempt, (dsn, database, concurrent.SerializeToString())).result(20)
    check(restored == ("APPROVAL_ALREADY_CONSUMED", 0), "Fresh process replayed saved confirmation")

    class UnknownTransport:
        calls = 0
        def execute(self, *_):
            self.calls += 1
            raise TimeoutError("synthetic unknown outcome")
    unknown = UnknownTransport()
    uncertain = CapabilityExecutor(unknown, ApprovalGuard(store))
    pending = receipt("unknown")
    result = uncertain.execute(plan(), ARGUMENTS, OWNER, approval_receipt=pending)
    check(not result.success and result.error_code == ExecutionErrorCode.TRANSPORT_TIMEOUT,
          "Unknown transport result became success")
    result = CapabilityExecutor(unknown, ApprovalGuard(PostgresApprovalStore(dsn, database))).execute(
        plan(), ARGUMENTS, OWNER, approval_receipt=pending)
    check(result.error_code == ExecutionErrorCode.APPROVAL_ALREADY_CONSUMED and unknown.calls == 1,
          "Unknown transport result was retried")

    control.execute(sql.SQL("REVOKE INSERT ON capability_approval_consumption FROM {}").format(sql.Identifier(role)))
    rejected(ExecutionErrorCode.APPROVAL_STORE_UNAVAILABLE, value=receipt("permission"))
    control.execute(sql.SQL("GRANT INSERT ON capability_approval_consumption TO {}").format(sql.Identifier(role)))
    check(executor.execute(plan("DESTRUCTIVE"), ARGUMENTS, OWNER,
                           approval_receipt=receipt("destructive", side_effect="DESTRUCTIVE")).success,
          "Confirmed destructive fixture did not execute")
    unavailable = CapabilityExecutor(transport, ApprovalGuard(PostgresApprovalStore(dsn, database + "_wrong")))
    before = len(transport.calls)
    result = unavailable.execute(plan(), ARGUMENTS, OWNER, approval_receipt=receipt("wrong-database"))
    check(result.error_code == ExecutionErrorCode.APPROVAL_STORE_UNAVAILABLE
          and len(transport.calls) == before, "Database identity mismatch did not fail closed")
    with psycopg.connect(dsn) as connection:
        check(connection.execute("SHOW transaction_read_only").fetchone()[0] == "on",
              "Consumption changed the role's read-only default")
    return {"concurrentAdmitted": 1, "concurrentRejected": 7, "freshProcessReplayCalls": 0,
            "unknownRetryDispatches": 0, "businessTransport": "recording/fault-injected",
            "externalBusinessCalls": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn-file", type=Path, required=True)
    parser.add_argument("--allow-disposable-database", action="store_true", required=True)
    args = parser.parse_args()
    if sys.flags.optimize:
        raise ValueError("Assertions must remain enabled")
    descriptor = os.open(args.dsn_file, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Owner-only regular DSN file required")
        dsn = stream.read(16385).strip()
    if not dsn or len(dsn) > 16384:
        raise ValueError("Invalid DSN size")
    fields = conninfo_to_dict(dsn)
    database, host = fields.get("dbname", ""), fields.get("host", "")
    if (not re.fullmatch(r"a2flow_capability_probe_[a-z0-9_]{1,32}", database)
            or host not in ("127.0.0.1", "::1", "localhost")
            or any(key in fields for key in ("service", "hostaddr", "options"))
            or os.environ.get("PGSERVICE") or os.environ.get("PGHOSTADDR")):
        raise ValueError("Explicit empty local a2flow_capability_probe_* database required")
    role = "capability_probe_" + uuid.uuid4().hex
    password = secrets.token_hex(24)
    table_created = role_created = False
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5,
                         options="-c statement_timeout=10000 -c lock_timeout=5000") as control:
        if control.info.dbname != database:
            raise ValueError("Database identity mismatch")
        if not control.execute("SELECT pg_try_advisory_lock(7808102003)").fetchone()[0]:
            raise ValueError("Another probe owns this database")
        if control.execute("SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                           "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema' "
                           "AND c.relkind IN ('r','p','v','m','f','S') LIMIT 1").fetchone():
            raise ValueError("Probe database must be empty")
        try:
            control.execute((ROOT / "services/management-java/backend/storage/db/migration/"
                             "V003__capability_approval_consumption.sql").read_text())
            table_created = True
            control.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)))
            role_created = True
            control.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only=on").format(sql.Identifier(role)))
            control.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            control.execute(sql.SQL("GRANT INSERT,SELECT ON capability_approval_consumption TO {}").format(sql.Identifier(role)))
            result = exercise(control, make_conninfo(dsn, user=role, password=password), database, role)
        finally:
            if table_created:
                control.execute("DROP TABLE capability_approval_consumption")
            if role_created:
                control.execute(sql.SQL("REVOKE USAGE ON SCHEMA public FROM {}").format(sql.Identifier(role)))
                control.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
    print(json.dumps({"probe": "capability-approval", "result": "PASS", "checks": CHECKS,
                      "postgres": True, "probeResourcesRemoved": True, **result}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # No SQL, DSN, role password or production-like traceback is published.
        detail = ": " + str(error) if isinstance(error, AssertionError) else ""
        print("Capability approval probe failed: " + type(error).__name__ + detail, file=sys.stderr)
        raise SystemExit(1) from None
