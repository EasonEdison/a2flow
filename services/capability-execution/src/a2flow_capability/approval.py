"""Final business admission. Only trusted hosts can supply typed confirmation receipts."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Protocol

from a2flow.capability.v1 import capability_pb2 as pb
from .models import CapabilityExecutionError, ExecutionErrorCode, JsonObject, PublishedPlan, TrustedContext


def argument_bytes(arguments: JsonObject) -> bytes:
    return json.dumps(arguments, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def requires_approval(plan: PublishedPlan) -> bool:
    if (plan.side_effect_level not in {"READ", "WRITE", "DESTRUCTIVE"}
            or plan.approval_policy not in {"AUTO_EXECUTE", "REQUEST_APPROVAL"}
            or (plan.side_effect_level != "READ" and plan.approval_policy != "REQUEST_APPROVAL")):
        raise CapabilityExecutionError(ExecutionErrorCode.EXECUTION_PLAN_INVALID,
                                       "Unsupported capability governance")
    return plan.side_effect_level != "READ"


class ApprovalStore(Protocol):
    def consume(self, receipt: pb.ApprovalReceipt) -> bool: ...


class PostgresApprovalStore:
    """A fresh committed claim; never joins the business transaction or retries RPC."""
    def __init__(self, dsn: str, database: str) -> None:
        self._dsn, self._database = dsn, database

    def consume(self, receipt: pb.ApprovalReceipt) -> bool:
        import psycopg
        with psycopg.connect(self._dsn, autocommit=True, connect_timeout=5,
                             options="-c statement_timeout=10000 -c default_transaction_read_only=off",
                             application_name="a2flow-capability-approval") as connection:
            if connection.info.dbname != self._database:
                raise ValueError("Approval database mismatch")
            row = connection.execute(
                "INSERT INTO capability_approval_consumption "
                "(receipt_id,user_id,environment,run_id,tool_call_id,action_code,source_id,source_digest,"
                "arguments_digest,confirmation_id,side_effect_level,approval_policy) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING receipt_id",
                (receipt.receipt_id, receipt.user_id, pb.Environment.Name(receipt.environment),
                 receipt.run_id, receipt.tool_call_id, receipt.action_code, receipt.source_id,
                 receipt.source_digest, receipt.arguments_digest, receipt.confirmation_id,
                 receipt.side_effect_level, receipt.approval_policy),
            ).fetchone()
            return row is not None


class ApprovalGuard:
    def __init__(self, store: ApprovalStore | None = None) -> None:
        self._store = store

    def admit(self, plan: PublishedPlan, arguments: JsonObject, owner: TrustedContext,
              receipt: pb.ApprovalReceipt | None, raw_json: bytes | None = None) -> None:
        if not requires_approval(plan):
            return
        if not isinstance(receipt, pb.ApprovalReceipt):
            raise CapabilityExecutionError(ExecutionErrorCode.APPROVAL_REQUIRED,
                                           "Explicit confirmation required before business write")
        raw = argument_bytes(arguments) if raw_json is None else raw_json
        # Never authorize a receipt for one byte payload while dispatching different data.
        try:
            equivalent = argument_bytes(json.loads(raw)) == argument_bytes(arguments)
        except (ValueError, TypeError, UnicodeError):
            equivalent = False
        identifiers = (receipt.receipt_id, receipt.confirmation_id, receipt.run_id, receipt.tool_call_id)
        if (not equivalent or any(not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,200}", value) for value in identifiers)
                or not receipt.HasField("user_id") or receipt.user_id != owner.user_id
                or receipt.environment != pb.Environment.Value(owner.environment.value)
                or receipt.action_code != plan.action_code or receipt.source_id != plan.source_id
                or receipt.source_digest != plan.source_digest
                or receipt.side_effect_level != plan.side_effect_level
                or receipt.approval_policy != plan.approval_policy
                or receipt.arguments_digest != hashlib.sha256(raw).hexdigest()):
            raise CapabilityExecutionError(ExecutionErrorCode.APPROVAL_INVALID,
                                           "Confirmation does not match immutable execution")
        try:
            if self._store is None:
                raise RuntimeError("Approval store not configured")
            consumed = self._store.consume(receipt)
        except Exception:
            raise CapabilityExecutionError(ExecutionErrorCode.APPROVAL_STORE_UNAVAILABLE,
                                           "Confirmation store unavailable; business not dispatched") from None
        if not consumed:
            raise CapabilityExecutionError(ExecutionErrorCode.APPROVAL_ALREADY_CONSUMED,
                                           "Confirmation already consumed; do not retry business execution")
