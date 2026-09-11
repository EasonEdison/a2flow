"""Versioned closed JSON records, never pickle or dynamically imported types."""

from dataclasses import asdict, fields
import json

from skillweave_contracts import TrustedInvocationContext

from .models import ActionRejected, ActionRequest, Attempt, Interaction


def _closed(value, cls, extra=()):
    if type(value) is not dict or set(value) != {f.name for f in fields(cls)} | set(extra):
        raise ValueError("closed record required")


def _text(value):
    if type(value) is not str or not value:
        raise ValueError("nonempty string required")
    return value


def _boolean(value):
    if type(value) is not bool:
        raise ValueError("boolean required")


def _json(value):
    result = json.loads(value)
    json.dumps(result, allow_nan=False)
    return result


def request_document(request):
    return {
        "runId": request.run_id, "nodeId": request.node_id,
        "interactionId": request.interaction_id, "actionName": request.action_name,
        "controlRequestId": request.control_request_id, "inputs": _json(request.inputs_json),
    }


def encode(interaction):
    document = asdict(interaction)
    document["context"] = interaction.context.to_mapping()
    document["recorded_versions"] = [list(pair) for pair in interaction.recorded_versions]
    document["attempts"] = [asdict(attempt) for attempt in interaction.attempts]
    document["schemaVersion"] = 1
    # Apply the same closed validation on writes and reads.
    decode(document)
    return document


def decode(document):
    try:
        _closed(document, Interaction, ("schemaVersion",))
        if type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1:
            raise ValueError("unsupported version")
        data = dict(document)
        del data["schemaVersion"]
        data["context"] = TrustedInvocationContext.from_mapping(data["context"])
        if data["context"].invocation_scope.kind != "WORKFLOW":
            raise ValueError("workflow required")
        for name in ("interaction_id", "application_key", "application_version", "graph_thread_id"):
            _text(data[name])
        for name in ("run_active", "node_waiting", "resume_started", "resume_consumed"):
            _boolean(data[name])
        if data["phase"] not in {"WAITING", "EXECUTING", "COMPLETED", "INVALIDATED"}:
            raise ValueError("invalid phase")
        if data["completion_request_id"] is not None:
            _text(data["completion_request_id"])
        versions = data["recorded_versions"]
        if type(versions) is not list or not versions:
            raise ValueError("version closure required")
        for pair in versions:
            if type(pair) is not list or len(pair) != 2:
                raise ValueError("version pair required")
            for value in pair:
                _text(value)
        if len({pair[0] for pair in versions}) != len(versions):
            raise ValueError("duplicate version")
        data["recorded_versions"] = tuple(tuple(pair) for pair in versions)
        if type(data["attempts"]) is not list:
            raise ValueError("attempt list required")
        attempts = []
        for raw in data["attempts"]:
            _closed(raw, Attempt)
            _closed(raw["request"], ActionRequest)
            req = ActionRequest(**raw["request"])
            canonical = ActionRequest.from_mapping(request_document(req))
            if req != canonical:
                raise ValueError("noncanonical request")
            if raw["status"] not in {"EXECUTING", "EXECUTED", "EXECUTION_UNCONFIRMED"}:
                raise ValueError("invalid execution status")
            if raw["resume_status"] not in {"NOT_REQUESTED", "DISPATCHING", "RETURNED", "UNCONFIRMED"}:
                raise ValueError("invalid resume status")
            _boolean(raw["business_success"])
            _boolean(raw["interaction_completed"])
            if raw["result_json"] is not None:
                _json(raw["result_json"])
            if raw["business_success"] and (raw["status"] != "EXECUTED" or raw["result_json"] is None):
                raise ValueError("success requires executed result")
            if raw["interaction_completed"] and not raw["business_success"]:
                raise ValueError("completion requires success")
            attempts.append(Attempt(**{**raw, "request": req}))
        data["attempts"] = tuple(attempts)
        result = Interaction(**data)
        if any(a.request.key != result.key for a in attempts):
            raise ValueError("attempt binding mismatch")
        ids = [a.request.control_request_id for a in attempts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate control request")
        completion = next((a for a in attempts if
                           a.request.control_request_id == result.completion_request_id), None)
        requires_completion = (result.phase == "COMPLETED" or result.resume_started
                               or result.resume_consumed or result.completion_request_id is not None)
        if requires_completion and (
            completion is None or completion.status != "EXECUTED"
            or not completion.business_success or not completion.interaction_completed
            or completion.result_json is None
        ):
            raise ValueError("real successful completion reference required")
        if result.resume_consumed and not result.resume_started:
            raise ValueError("consumption requires dispatch reservation")
        if result.completion_request_id is not None and result.phase not in {"COMPLETED", "INVALIDATED"}:
            raise ValueError("completion phase mismatch")
        if result.resume_started and completion.resume_status == "NOT_REQUESTED":
            raise ValueError("dispatch reservation required")
        return result
    except Exception:
        raise ActionRejected("INVALID_STORED_RECORD") from None
