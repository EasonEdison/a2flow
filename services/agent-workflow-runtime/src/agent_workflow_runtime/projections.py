"""Whitelist-only progress observations; no raw results or invented liveness."""

from datetime import datetime, timezone

from .models import ActionRejected
from .service import identifier

COLLECTION_LIMIT = 100


def _enum(value, allowed):
    if value not in allowed:
        raise ActionRejected("PROJECTION_UNAVAILABLE")
    return value


def _number(value):
    if type(value) is not int or value < 0:
        raise ActionRejected("PROJECTION_UNAVAILABLE")
    return value


def _boolean(value):
    if type(value) is not bool:
        raise ActionRejected("PROJECTION_UNAVAILABLE")
    return value


def receipt(row, control_id):
    if row is None:
        raise ActionRejected("CONTROL_NOT_FOUND")
    return {"controlRequestId": identifier(control_id),
            "runId": identifier(row["run_id"]),
            "delivery": _enum(row["status"], {"DISPATCHING", "RETURNED", "UNCONFIRMED"})}


def snapshot(run, operations, interactions):
    if run is None:
        raise ActionRejected("RUN_NOT_FOUND")
    status = _enum(run["status"], {"RUNNING", "STOPPED", "SUCCEEDED"})
    observed_operations = [
        {"nodeId": identifier(row["node_id"]),
         "kind": _enum(row["kind"], {"NODE", "ROUTER", "MODEL", "TOOL", "ACTION", "FINALIZER", "RETRY"}),
         "recordedStatus": _enum(row["status"], {"IN_FLIGHT", "RETURNED", "INTERRUPTED", "UNCONFIRMED"}),
         "count": _number(row["count"])}
        for row in operations[:COLLECTION_LIMIT]
    ]
    cards = []
    for row in interactions[:COLLECTION_LIMIT]:
        phase = _enum(row["phase"], {"WAITING", "EXECUTING", "COMPLETED", "INVALIDATED"})
        candidate = (status == "RUNNING" and phase == "WAITING"
                     and _boolean(row["run_active"]) and _boolean(row["node_waiting"]))
        item = {
            "nodeId": identifier(row["node_id"]),
            "interactionId": identifier(row["interaction_id"]),
            "recordedPhase": phase,
            # This is not authorization: Action admission still checks current versions.
            "actionEligibility": "REVALIDATION_REQUIRED" if candidate else "NOT_OPERABLE",
            "attemptCount": _number(row["attempt_count"]),
        }
        if row["attempt_count"]:
            item["lastAttempt"] = {
                "controlRequestId": identifier(row["control_id"]),
                "status": _enum(row["attempt_status"], {"EXECUTING", "EXECUTED", "EXECUTION_UNCONFIRMED"}),
                "businessSuccess": _boolean(row["business_success"]),
                "interactionCompleted": _boolean(row["interaction_completed"]),
                "resumeDelivery": _enum(row["resume_status"], {"NOT_REQUESTED", "DISPATCHING", "RETURNED", "UNCONFIRMED"}),
            }
        cards.append(item)
    return {
        "runId": identifier(run["run_id"]), "lifecycle": status,
        "lifecycleRevision": _number(run["revision"]),
        "initialControl": {"controlRequestId": identifier(run["initial_control_id"]),
                           "delivery": _enum(run["initial_control_status"], {"DISPATCHING", "RETURNED", "UNCONFIRMED"})},
        "observedAt": datetime.now(timezone.utc).isoformat(),
        "consistency": "COMMITTED_SNAPSHOT",
        "nativeExecution": {"liveness": "NOT_ESTABLISHED", "waiting": "NOT_INSPECTED"},
        "operationHistory": {"items": observed_operations, "truncated": len(operations) > COLLECTION_LIMIT},
        "interactions": {"items": cards, "truncated": len(interactions) > COLLECTION_LIMIT},
    }
