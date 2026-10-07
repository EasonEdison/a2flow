"""Durable, conversation-scoped A2UI card lifecycle storage.

The store owns platform request deduplication only. It commits a request claim
before business dispatch and never guesses whether an uncertain operation is
safe to retry. Business retries and compensation remain outside this module.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, Literal, Never, TypeAlias, TypedDict, cast
from collections.abc import Callable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from skillweave_contracts import TrustedContext

from ..application_runtime import PreparedApplication
from ..models import ActionRejected

_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,127}")
_MAX_DISPLAY_BYTES = 1_048_576
_MAX_METADATA_BYTES = 262_144
_MAX_INPUT_BYTES = 65_536
_MAX_RESULT_BYTES = 262_144
_MAX_OBSERVATION_BYTES = _MAX_RESULT_BYTES + _MAX_METADATA_BYTES + _MAX_INPUT_BYTES

JsonValue: TypeAlias = (
    bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None
)
JsonObject: TypeAlias = dict[str, JsonValue]
Scope: TypeAlias = tuple[str, int, str]
ObservationKind: TypeAlias = Literal["RENDERED", "ACTION"]
ObservationStatus: TypeAlias = Literal["SUCCEEDED", "FAILED", "UNKNOWN", "REJECTED"]
PresentationStatus: TypeAlias = Literal["SUCCEEDED", "FAILED"]


@dataclass(frozen=True, slots=True)
class ActionObservation:
    arguments: JsonObject
    result: JsonValue
    capability_success: bool
    business_success: bool | None
    description: str | None = None
    presentation_status: PresentationStatus = "SUCCEEDED"
    presentation_error_code: str | None = None
    capability_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ChatObservation:
    sequence: int
    event_id: str
    kind: ObservationKind
    card_id: str
    application_key: str
    request_id: str | None = None
    action_name: str | None = None
    description: str | None = None
    arguments: JsonObject | None = None
    status: ObservationStatus | None = None
    result: JsonValue = None
    capability_success: bool | None = None
    business_success: bool | None = None
    presentation_status: PresentationStatus | None = None
    capability_error_code: str | None = None
    presentation_error_code: str | None = None
    error_code: str | None = None


class ObservationRow(TypedDict):
    sequence: int
    event_id: str
    payload: JsonObject


DDL = (
    """CREATE TABLE IF NOT EXISTS chat_a2ui_cards (
        environment TEXT NOT NULL, user_id BIGINT NOT NULL,
        conversation_id TEXT NOT NULL, card_id TEXT NOT NULL,
        display JSONB NOT NULL, binding_metadata JSONB NOT NULL,
        status TEXT NOT NULL CHECK (status IN
          ('WAITING_ACTION','DISPLAY_ONLY','EXECUTING','COMPLETED','UNKNOWN')),
        revision BIGINT NOT NULL CHECK (revision >= 0), result JSONB,
        has_result BOOLEAN NOT NULL DEFAULT FALSE, active_request_id TEXT,
        save_fingerprint TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY (environment,user_id,conversation_id,card_id)
    )""",
    """CREATE TABLE IF NOT EXISTS chat_a2ui_action_requests (
        environment TEXT NOT NULL, user_id BIGINT NOT NULL,
        conversation_id TEXT NOT NULL, card_id TEXT NOT NULL,
        request_id TEXT NOT NULL, payload JSONB NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('CLAIMED','FINISHED','UNKNOWN')),
        result JSONB, finish_payload JSONB, error_code TEXT, card_snapshot JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY (environment,user_id,conversation_id,card_id,request_id),
        FOREIGN KEY (environment,user_id,conversation_id,card_id)
          REFERENCES chat_a2ui_cards(environment,user_id,conversation_id,card_id)
    )""",
    """CREATE TABLE IF NOT EXISTS chat_a2ui_observation_heads (
        environment TEXT NOT NULL, user_id BIGINT NOT NULL,
        conversation_id TEXT NOT NULL, next_sequence BIGINT NOT NULL DEFAULT 1
          CHECK (next_sequence > 0),
        PRIMARY KEY (environment,user_id,conversation_id)
    )""",
    """CREATE TABLE IF NOT EXISTS chat_a2ui_observations (
        environment TEXT NOT NULL, user_id BIGINT NOT NULL,
        conversation_id TEXT NOT NULL, sequence BIGINT NOT NULL CHECK (sequence > 0),
        event_id TEXT NOT NULL, payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY (environment,user_id,conversation_id,sequence),
        UNIQUE (environment,user_id,conversation_id,event_id)
    )""",
    """CREATE INDEX IF NOT EXISTS chat_a2ui_cards_conversation_order
       ON chat_a2ui_cards(environment,user_id,conversation_id,created_at,card_id)""",
)


def _reject(code: str) -> Never:
    raise ActionRejected(code)


def _identifier(value, code="INVALID_CARD_INPUT", *, limit=128):
    if type(value) is not str or not value or len(value) > limit:
        _reject(code)
    return value


def _json_copy(value, code, limit):
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > limit:
            _reject(code)
        return json.loads(encoded), encoded
    except ActionRejected:
        raise
    except (TypeError, ValueError, RecursionError, UnicodeError):
        _reject(code)


def _owner(owner, environment):
    if type(owner) is not TrustedContext:
        _reject("TRUSTED_CONTEXT_REQUIRED")
    if owner.environment != environment:
        _reject("CARD_ENVIRONMENT_MISMATCH")
    return owner


def _scope(owner, conversation_id):
    return owner.environment, owner.user_id, conversation_id


def _public(card):
    value = {"cardId": card["card_id"],
             "conversationId": card["conversation_id"],
             "display": deepcopy(card["display"]), "status": card["status"],
             }
    metadata = card.get("binding_metadata")
    control_request_id = (
        metadata.get("controlRequestId") if isinstance(metadata, dict) else None
    )
    if (isinstance(control_request_id, str)
            and control_request_id.startswith("chat-")
            and control_request_id[5:]):
        # The composition root creates Chat control ids from the durable input
        # message id. Publish the relation explicitly so clients never infer it
        # from card or message position.
        value["turnId"] = control_request_id[5:]
    if card["has_result"]:
        value["result"] = deepcopy(card["result"])
    return value


def _card_id(owner, conversation_id, control_request_id, tool_call_id):
    material = json.dumps([owner.user_id, owner.environment, conversation_id,
                           control_request_id, tool_call_id],
                          separators=(",", ":"), ensure_ascii=True)
    return "card:" + sha256(material.encode()).hexdigest()


def _validate_metadata(value, conversation_id):
    copied, _ = _json_copy(value, "INVALID_CARD_METADATA", _MAX_METADATA_BYTES)
    required = {"skillKey", "conversationId",
                "controlRequestId", "toolCallId"}
    if type(copied) is not dict or not required.issubset(copied):
        _reject("INVALID_CARD_METADATA")
    _identifier(copied["skillKey"], "INVALID_CARD_METADATA")
    _identifier(copied["controlRequestId"], "INVALID_CARD_METADATA", limit=256)
    _identifier(copied["toolCallId"], "INVALID_CARD_METADATA", limit=256)
    if copied["conversationId"] != conversation_id:
        _reject("CARD_CONVERSATION_MISMATCH")
    return copied


def _validate_prepared(prepared):
    if type(prepared) is not PreparedApplication:
        _reject("PREPARED_APPLICATION_REQUIRED")
    display, _ = _json_copy(prepared.display(), "INVALID_CARD_DISPLAY",
                            _MAX_DISPLAY_BYTES)
    if (type(prepared.interactive) is not bool or type(display) is not dict
            or type(display.get("actions")) is not list):
        _reject("INVALID_CARD_DISPLAY")
    names = []
    rpc_profile = display.get("protocolProfile") == "a2flow.java-rpc.v1"
    for action in display["actions"]:
        if (type(action) is not dict or type(action.get("actionName")) is not str
                or not action["actionName"] or len(action["actionName"]) > 128):
            _reject("INVALID_CARD_DISPLAY")
        if rpc_profile:
            for field in ("surfaceId", "componentId"):
                _identifier(action.get(field), "INVALID_CARD_DISPLAY")
            names.append((action["surfaceId"], action["componentId"], action["actionName"]))
        else:
            names.append(action["actionName"])
    if len(names) != len(set(names)) or (not rpc_profile and prepared.interactive != bool(names)):
        _reject("INVALID_CARD_DISPLAY")
    return display, "WAITING_ACTION" if prepared.interactive else "DISPLAY_ONLY"


def _action_is_bound(card, action_name):
    return any(type(action) is dict and action.get("actionName") == action_name
               for action in card["display"].get("actions", ()))


def _persist_option_selection(display, inputs):
    if "optionId" not in inputs:
        return deepcopy(display)
    option_id = inputs["optionId"]
    if type(option_id) is not str or not option_id or len(option_id) > 128:
        _reject("INVALID_OPTION_ID")
    data = display.get("data")
    options = data.get("options") if type(data) is dict else None
    if (type(options) is not list or not any(
            type(option) is dict and option.get("value") == option_id
            for option in options)):
        _reject("INVALID_OPTION_ID")
    updated = deepcopy(display)
    updated["data"]["optionId"] = option_id
    return updated


def _event_payload(
    card: dict[str, Any],
    *,
    kind: ObservationKind,
    request_id: str | None = None,
    action_name: str | None = None,
    description: str | None = None,
    arguments: JsonObject | None = None,
    status: ObservationStatus | None = None,
    result: JsonValue = None,
    capability_success: bool | None = None,
    business_success: bool | None = None,
    presentation_status: PresentationStatus | None = None,
    capability_error_code: str | None = None,
    presentation_error_code: str | None = None,
    error_code: str | None = None,
) -> JsonObject:
    value = {"kind": kind, "cardId": card["card_id"],
             "applicationKey": card["display"]["applicationKey"]}
    optional = {"requestId": request_id, "actionName": action_name,
                "description": description, "arguments": arguments,
                "status": status, "result": result,
                "capabilitySuccess": capability_success,
                "businessSuccess": business_success,
                "presentationStatus": presentation_status,
                "capabilityErrorCode": capability_error_code,
                "presentationErrorCode": presentation_error_code,
                "errorCode": error_code}
    value.update({key: item for key, item in optional.items() if item is not None})
    copied, _ = _json_copy(value, "INVALID_CHAT_OBSERVATION", _MAX_OBSERVATION_BYTES)
    if copied["kind"] not in {"RENDERED", "ACTION"}:
        _reject("INVALID_CHAT_OBSERVATION")
    return cast(JsonObject, copied)


def _typed_observation(row: ObservationRow) -> ChatObservation:
    value = cast(JsonObject, deepcopy(row["payload"]))
    return ChatObservation(
        sequence=cast(int, row["sequence"]), event_id=cast(str, row["event_id"]),
        kind=cast(ObservationKind, value["kind"]),
        card_id=cast(str, value["cardId"]),
        application_key=cast(str, value["applicationKey"]),
        request_id=cast(str | None, value.get("requestId")),
        action_name=cast(str | None, value.get("actionName")),
        description=cast(str | None, value.get("description")),
        arguments=cast(JsonObject | None, value.get("arguments")),
        status=cast(ObservationStatus | None, value.get("status")),
        result=cast(JsonValue, value.get("result")),
        capability_success=cast(bool | None, value.get("capabilitySuccess")),
        business_success=cast(bool | None, value.get("businessSuccess")),
        presentation_status=cast(PresentationStatus | None, value.get("presentationStatus")),
        capability_error_code=cast(str | None, value.get("capabilityErrorCode")),
        presentation_error_code=cast(str | None, value.get("presentationErrorCode")),
        error_code=cast(str | None, value.get("errorCode")),
    )


@dataclass(frozen=True, slots=True)
class CardCompletion:
    owner: TrustedContext
    conversation_id: str
    card_id: str
    request_id: str
    metadata: JsonObject


CompletionObserver: TypeAlias = Callable[
    [psycopg.Connection[Any], CardCompletion], None
]


class ChatCardStore:
    """PostgreSQL card store with an explicit test-only storage injection seam."""

    def __init__(self, conninfo, *, environment, _storage=None,
                 completion_observer: CompletionObserver | None = None):
        if environment not in {"PRT", "ONLINE"}:
            raise ValueError("CARD_ENVIRONMENT_REQUIRED")
        if _storage is None:
            if type(conninfo) is not str or not conninfo or len(conninfo) > 4096:
                raise ValueError("CARD_CONNINFO_REQUIRED")
            _storage = _PostgresStorage(conninfo)
        self._environment, self._storage = environment, _storage
        self._completion_observer = completion_observer

    def setup(self):
        """Create only the isolated card tables; never runs from request paths."""
        self._storage.setup()

    def save(self, owner, conversation_id, prepared, binding_metadata):
        owner = _owner(owner, self._environment)
        conversation_id = _identifier(conversation_id, "INVALID_CONVERSATION_ID")
        display, status = _validate_prepared(prepared)
        metadata = _validate_metadata(binding_metadata, conversation_id)
        card_id = _card_id(owner, conversation_id, metadata["controlRequestId"],
                           metadata["toolCallId"])
        fingerprint_source = {"display": display, "metadata": metadata,
                              "status": status}
        _, canonical = _json_copy(fingerprint_source, "INVALID_CARD_INPUT",
                                  _MAX_DISPLAY_BYTES + _MAX_METADATA_BYTES)
        card = {"environment": owner.environment, "user_id": owner.user_id,
                "conversation_id": conversation_id, "card_id": card_id,
                "display": display, "binding_metadata": metadata, "status": status,
                "revision": 0, "result": None, "has_result": False,
                "active_request_id": None,
                "save_fingerprint": sha256(canonical.encode()).hexdigest()}
        with self._storage.transaction() as transaction:
            inserted = transaction.insert_card(card)
            stored = transaction.get_card(_scope(owner, conversation_id), card_id,
                                           lock=True)
            if stored is None:
                _reject("CARD_STORE_OPERATION_UNCONFIRMED")
            if not inserted and stored["save_fingerprint"] != card["save_fingerprint"]:
                _reject("CARD_REPLAY_CONFLICT")
            if inserted:
                observed = metadata.get("observation")
                description = observed.get("description") if type(observed) is dict else None
                arguments = observed.get("arguments") if type(observed) is dict else None
                if description is not None and type(description) is not str:
                    _reject("INVALID_CHAT_OBSERVATION")
                if arguments is not None and type(arguments) is not dict:
                    _reject("INVALID_CHAT_OBSERVATION")
                transaction.append_observation(
                    _scope(owner, conversation_id),
                    card_id + ":rendered",
                    _event_payload(card, kind="RENDERED", description=description,
                                   arguments=cast(JsonObject | None, arguments)),
                )
            return _public(stored)

    def list(self, owner, conversation_id):
        owner = _owner(owner, self._environment)
        conversation_id = _identifier(conversation_id, "INVALID_CONVERSATION_ID")
        with self._storage.transaction() as transaction:
            return [_public(card) for card in transaction.list_cards(
                _scope(owner, conversation_id))]

    def read(self, owner, conversation_id, card_id):
        owner = _owner(owner, self._environment)
        conversation_id = _identifier(conversation_id, "INVALID_CONVERSATION_ID")
        card_id = _identifier(card_id, "INVALID_CARD_ID", limit=128)
        with self._storage.transaction() as transaction:
            card = transaction.get_card(_scope(owner, conversation_id), card_id)
            return None if card is None else _public(card)

    def get_binding(self, owner: TrustedContext, conversation_id: str, card_id: str) -> dict[str, Any]:
        owner = _owner(owner, self._environment)
        conversation_id = _identifier(conversation_id, "INVALID_CONVERSATION_ID")
        card_id = _identifier(card_id, "INVALID_CARD_ID", limit=128)
        with self._storage.transaction() as transaction:
            card = transaction.get_card(_scope(owner, conversation_id), card_id)
            if card is None:
                _reject("CARD_NOT_FOUND")
            return {"card": _public(card),
                    "metadata": deepcopy(card["binding_metadata"])}

    def list_observations(
        self, owner: TrustedContext, conversation_id: str, *, after_sequence: int,
        limit: int = 100,
    ) -> list[ChatObservation]:
        """Read one committed conversation prefix; no acknowledgement is stored here."""

        owner = _owner(owner, self._environment)
        conversation_id = _identifier(conversation_id, "INVALID_CONVERSATION_ID")
        if type(after_sequence) is not int or after_sequence < 0:
            _reject("INVALID_OBSERVATION_CURSOR")
        if type(limit) is not int or limit < 1 or limit > 100:
            _reject("INVALID_OBSERVATION_LIMIT")
        with self._storage.transaction() as transaction:
            return [_typed_observation(row) for row in transaction.list_observations(
                _scope(owner, conversation_id), after_sequence, limit)]

    def replay(self, owner: TrustedContext, conversation_id: str, card_id: str, request_id: str,
               action_name: str, inputs: dict[str, Any]) -> dict[str, Any] | None:
        """Return a completed receipt before reinterpreting a newer publication."""
        owner = _owner(owner, self._environment)
        conversation_id = _identifier(conversation_id, "INVALID_CONVERSATION_ID")
        card_id = _identifier(card_id, "INVALID_CARD_ID", limit=128)
        request_id = _identifier(request_id, "INVALID_REQUEST_ID", limit=256)
        payload = {"actionName": action_name, "inputs": inputs}
        with self._storage.transaction() as transaction:
            request = transaction.get_request(_scope(owner, conversation_id), card_id, request_id)
            if request is None:
                return None
            if request["payload"] != payload:
                _reject("ACTION_REQUEST_CONFLICT")
            if request["state"] == "FINISHED":
                return deepcopy(request["card_snapshot"])
            if request["state"] == "UNKNOWN":
                _reject("ACTION_OUTCOME_UNKNOWN")
            _reject("ACTION_REQUEST_BUSY")

    def claim(self, owner: TrustedContext, conversation_id: str, card_id: str, request_id: str,
              action_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        owner = _owner(owner, self._environment)
        conversation_id = _identifier(conversation_id, "INVALID_CONVERSATION_ID")
        card_id = _identifier(card_id, "INVALID_CARD_ID", limit=128)
        request_id = _identifier(request_id, "INVALID_REQUEST_ID", limit=256)
        action_name = _identifier(action_name, "INVALID_ACTION_NAME")
        inputs, _ = _json_copy(inputs, "INVALID_ACTION_INPUT", _MAX_INPUT_BYTES)
        if type(inputs) is not dict:
            _reject("INVALID_ACTION_INPUT")
        payload = {"actionName": action_name, "inputs": inputs}
        scope = _scope(owner, conversation_id)
        with self._storage.transaction() as transaction:
            card = transaction.get_card(scope, card_id, lock=True)
            if card is None:
                _reject("CARD_NOT_FOUND")
            request = transaction.get_request(scope, card_id, request_id, lock=True)
            if request is not None:
                if request["payload"] != payload:
                    _reject("ACTION_REQUEST_CONFLICT")
                if request["state"] == "FINISHED":
                    finish = request["finish_payload"]
                    return {"dispatch": False,
                            "card": deepcopy(request["card_snapshot"]),
                            "metadata": deepcopy(card["binding_metadata"]),
                            "result": deepcopy(request["result"]),
                            "businessSuccess": finish["businessSuccess"],
                            "completes": finish["completes"]}
                if request["state"] == "UNKNOWN":
                    _reject("ACTION_OUTCOME_UNKNOWN")
                _reject("ACTION_REQUEST_BUSY")
            if card["status"] == "EXECUTING":
                _reject("CARD_BUSY")
            if card["status"] in {"COMPLETED", "UNKNOWN"}:
                _reject("CARD_TERMINAL")
            rpc_display = (card["status"] == "DISPLAY_ONLY" and
                           card["display"].get("protocolProfile") == "a2flow.java-rpc.v1")
            if card["status"] != "WAITING_ACTION" and not rpc_display:
                _reject("CARD_NOT_ACTIONABLE")
            if not _action_is_bound(card, action_name):
                _reject("ACTION_NOT_BOUND")
            request = {"environment": owner.environment, "user_id": owner.user_id,
                       "conversation_id": conversation_id, "card_id": card_id,
                       "request_id": request_id, "payload": payload,
                       "state": "CLAIMED", "result": None,
                       "finish_payload": None, "error_code": None,
                       "card_snapshot": None}
            transaction.insert_request(request)
            card["status"], card["revision"] = "EXECUTING", card["revision"] + 1
            card["active_request_id"] = request_id
            transaction.update_card(card)
            return {"dispatch": True, "card": _public(card),
                    "metadata": deepcopy(card["binding_metadata"])}

    def finish(self, owner: TrustedContext, conversation_id: str, card_id: str, request_id: str,
               result: Any, business_success: bool, completes: bool, *,
               prepared: PreparedApplication | None = None,
               binding_metadata: dict[str, Any] | None = None,
               observation: ActionObservation | None = None,
               observation_status: ObservationStatus | None = None) -> dict[str, Any]:
        owner = _owner(owner, self._environment)
        conversation_id = _identifier(conversation_id, "INVALID_CONVERSATION_ID")
        card_id = _identifier(card_id, "INVALID_CARD_ID", limit=128)
        request_id = _identifier(request_id, "INVALID_REQUEST_ID", limit=256)
        result, _ = _json_copy(result, "INVALID_ACTION_RESULT", _MAX_RESULT_BYTES)
        if type(business_success) is not bool or type(completes) is not bool:
            _reject("INVALID_ACTION_OUTCOME")
        finish_payload = {"result": result, "businessSuccess": business_success,
                          "completes": completes,
                          "observationStatus": observation_status,
                          "observation": (None if observation is None
                                          else asdict(observation))}
        update = None
        if prepared is not None or binding_metadata is not None:
            display, waiting_status = _validate_prepared(prepared)
            metadata = _validate_metadata(binding_metadata, conversation_id)
            if display.get("protocolProfile") != "a2flow.java-rpc.v1":
                _reject("INVALID_CARD_DISPLAY")
            update = (display, waiting_status, metadata)
            finish_payload["runtimeUpdate"] = {"display": display, "metadata": metadata,
                                               "waitingStatus": waiting_status}
        scope = _scope(owner, conversation_id)
        with self._storage.transaction() as transaction:
            card = transaction.get_card(scope, card_id, lock=True)
            if card is None:
                _reject("CARD_NOT_FOUND")
            request = transaction.get_request(scope, card_id, request_id, lock=True)
            if request is None:
                _reject("ACTION_REQUEST_NOT_CLAIMED")
            if request["state"] == "FINISHED":
                if request["finish_payload"] != finish_payload:
                    _reject("ACTION_FINISH_CONFLICT")
                return deepcopy(request["card_snapshot"])
            if request["state"] == "UNKNOWN":
                _reject("ACTION_OUTCOME_UNKNOWN")
            if card["status"] != "EXECUTING" or card["active_request_id"] != request_id:
                _reject("ACTION_REQUEST_NOT_ACTIVE")
            waiting_status = "WAITING_ACTION"
            if update is None:
                card["display"] = _persist_option_selection(
                    card["display"], request["payload"]["inputs"])
            else:
                display, waiting_status, metadata = update
                # Only trusted runtime state changes; card and Skill ownership cannot change.
                for field in ("skillKey", "conversationId", "controlRequestId", "toolCallId",
                              "applicationKey"):
                    if metadata.get(field) != card["binding_metadata"].get(field):
                        _reject("CARD_BINDING_MISMATCH")
                if display["applicationKey"] != card["display"]["applicationKey"]:
                    _reject("CARD_BINDING_MISMATCH")
                card["display"], card["binding_metadata"] = display, metadata
            card["status"] = ("COMPLETED" if business_success and completes
                              else waiting_status)
            card["revision"] += 1
            card["result"], card["has_result"] = result, True
            card["active_request_id"] = None
            request["state"], request["result"] = "FINISHED", result
            request["finish_payload"] = finish_payload
            request["card_snapshot"] = _public(card)
            transaction.update_card(card)
            transaction.update_request(request)
            transaction.append_observation(
                scope, "action:" + card_id + ":" + request_id,
                _event_payload(
                    card, kind="ACTION", request_id=request_id,
                    action_name=request["payload"]["actionName"],
                    description=None if observation is None else observation.description,
                    arguments=None if observation is None else observation.arguments,
                    status=(observation_status or
                            ("SUCCEEDED" if business_success else "FAILED")),
                    result=result if observation is None else observation.result,
                    capability_success=(None if observation is None
                                        else observation.capability_success),
                    business_success=(
                        None if observation is None and observation_status == "REJECTED"
                        else business_success if observation is None
                        else observation.business_success
                    ),
                    presentation_status=(None if observation is None
                                         else observation.presentation_status),
                    capability_error_code=(None if observation is None
                                           else observation.capability_error_code),
                    presentation_error_code=(None if observation is None
                                             else observation.presentation_error_code),
                    error_code=None,
                ),
            )
            if card["status"] == "COMPLETED" and self._completion_observer is not None:
                self._completion_observer(
                    transaction._connection,
                    CardCompletion(owner, conversation_id, card_id, request_id,
                                   cast(JsonObject, deepcopy(card["binding_metadata"]))),
                )
            return _public(card)

    def fail(self, owner: TrustedContext, conversation_id: str, card_id: str, request_id: str,
             error_code: str, *, observation: ActionObservation | None = None) -> dict[str, Any]:
        owner = _owner(owner, self._environment)
        conversation_id = _identifier(conversation_id, "INVALID_CONVERSATION_ID")
        card_id = _identifier(card_id, "INVALID_CARD_ID", limit=128)
        request_id = _identifier(request_id, "INVALID_REQUEST_ID", limit=256)
        if type(error_code) is not str or _ERROR_CODE.fullmatch(error_code) is None:
            _reject("INVALID_ERROR_CODE")
        scope = _scope(owner, conversation_id)
        with self._storage.transaction() as transaction:
            card = transaction.get_card(scope, card_id, lock=True)
            if card is None:
                _reject("CARD_NOT_FOUND")
            request = transaction.get_request(scope, card_id, request_id, lock=True)
            if request is None:
                _reject("ACTION_REQUEST_NOT_CLAIMED")
            if request["state"] == "UNKNOWN":
                if request["error_code"] != error_code:
                    _reject("ACTION_FAILURE_CONFLICT")
                return deepcopy(request["card_snapshot"])
            if request["state"] == "FINISHED":
                _reject("ACTION_REQUEST_ALREADY_FINISHED")
            if card["status"] != "EXECUTING" or card["active_request_id"] != request_id:
                _reject("ACTION_REQUEST_NOT_ACTIVE")
            card["status"], card["revision"] = "UNKNOWN", card["revision"] + 1
            card["active_request_id"] = None
            request["state"], request["error_code"] = "UNKNOWN", error_code
            request["card_snapshot"] = _public(card)
            transaction.update_card(card)
            transaction.update_request(request)
            transaction.append_observation(
                scope, "action:" + card_id + ":" + request_id,
                _event_payload(
                    card, kind="ACTION", request_id=request_id,
                    action_name=request["payload"]["actionName"],
                    description=None if observation is None else observation.description,
                    arguments=None if observation is None else observation.arguments,
                    status=("UNKNOWN" if observation is None
                            or observation.business_success is None
                            else "SUCCEEDED" if observation.business_success else "FAILED"),
                    result=None if observation is None else observation.result,
                    capability_success=(None if observation is None
                                        else observation.capability_success),
                    business_success=(None if observation is None
                                      else observation.business_success),
                    presentation_status=(None if observation is None
                                         else observation.presentation_status),
                    capability_error_code=(None if observation is None
                                           else observation.capability_error_code),
                    presentation_error_code=(None if observation is None
                                             else observation.presentation_error_code),
                    error_code=error_code,
                ),
            )
            return _public(card)


class _PostgresStorage:
    def __init__(self, conninfo):
        self._conninfo = conninfo

    def _connect(self):
        return psycopg.connect(self._conninfo, row_factory=dict_row, connect_timeout=5,
            options="-c lock_timeout=5000 -c statement_timeout=10000",
            application_name="a2flow-chat-cards")

    def setup(self):
        try:
            with self._connect() as connection, connection.transaction():
                for statement in DDL:
                    connection.execute(statement)
        except Exception:
            _reject("CARD_STORE_SETUP_FAILED")

    @contextmanager
    def transaction(self):
        try:
            with self._connect() as connection, connection.transaction():
                yield _PostgresTransaction(connection)
        except ActionRejected:
            raise
        except Exception:
            _reject("CARD_STORE_OPERATION_UNCONFIRMED")


class _PostgresTransaction:
    def __init__(self, connection):
        self._connection = connection

    def insert_card(self, card):
        row = self._connection.execute(
            """INSERT INTO chat_a2ui_cards
               (environment,user_id,conversation_id,card_id,display,binding_metadata,
                status,revision,result,has_result,active_request_id,save_fingerprint)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT DO NOTHING RETURNING card_id""",
            (card["environment"], card["user_id"], card["conversation_id"],
             card["card_id"], Jsonb(card["display"]), Jsonb(card["binding_metadata"]),
             card["status"], card["revision"], Jsonb(card["result"]),
             card["has_result"], card["active_request_id"], card["save_fingerprint"])
        ).fetchone()
        return row is not None

    def get_card(self, scope, card_id, lock=False):
        statement = """SELECT environment,user_id,conversation_id,card_id,display,
          binding_metadata,status,revision,result,has_result,active_request_id,
          save_fingerprint FROM chat_a2ui_cards WHERE environment=%s AND user_id=%s
          AND conversation_id=%s AND card_id=%s""" + (" FOR UPDATE" if lock else "")
        row = self._connection.execute(statement, (*scope, card_id)).fetchone()
        return None if row is None else dict(row)

    def list_cards(self, scope):
        rows = self._connection.execute(
            """SELECT environment,user_id,conversation_id,card_id,display,
              binding_metadata,status,revision,result,has_result,active_request_id,
              save_fingerprint FROM chat_a2ui_cards WHERE environment=%s AND user_id=%s
              AND conversation_id=%s ORDER BY created_at,card_id""", scope).fetchall()
        return [dict(row) for row in rows]

    def update_card(self, card):
        row = self._connection.execute(
            """UPDATE chat_a2ui_cards SET display=%s,binding_metadata=%s,status=%s,revision=%s,result=%s,
              has_result=%s,active_request_id=%s,updated_at=clock_timestamp()
              WHERE environment=%s AND user_id=%s AND conversation_id=%s AND card_id=%s
              RETURNING card_id""",
            (Jsonb(card["display"]), Jsonb(card["binding_metadata"]), card["status"], card["revision"],
             Jsonb(card["result"]), card["has_result"], card["active_request_id"],
             card["environment"], card["user_id"], card["conversation_id"],
             card["card_id"])).fetchone()
        if row is None:
            _reject("CARD_STORE_OPERATION_UNCONFIRMED")

    def insert_request(self, request):
        row = self._connection.execute(
            """INSERT INTO chat_a2ui_action_requests
              (environment,user_id,conversation_id,card_id,request_id,payload,state,
               result,finish_payload,error_code,card_snapshot)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
              ON CONFLICT DO NOTHING RETURNING request_id""",
            (request["environment"], request["user_id"], request["conversation_id"],
             request["card_id"], request["request_id"], Jsonb(request["payload"]),
             request["state"], Jsonb(request["result"]), Jsonb(request["finish_payload"]),
             request["error_code"], Jsonb(request["card_snapshot"]))).fetchone()
        if row is None:
            _reject("ACTION_REQUEST_CONFLICT")

    def get_request(self, scope, card_id, request_id, lock=False):
        statement = """SELECT environment,user_id,conversation_id,card_id,request_id,
          payload,state,result,finish_payload,error_code,card_snapshot
          FROM chat_a2ui_action_requests WHERE environment=%s AND user_id=%s
          AND conversation_id=%s AND card_id=%s AND request_id=%s"""
        if lock:
            statement += " FOR UPDATE"
        row = self._connection.execute(statement, (*scope, card_id, request_id)).fetchone()
        return None if row is None else dict(row)

    def update_request(self, request):
        row = self._connection.execute(
            """UPDATE chat_a2ui_action_requests SET state=%s,result=%s,
              finish_payload=%s,error_code=%s,card_snapshot=%s,
              updated_at=clock_timestamp() WHERE environment=%s AND user_id=%s
              AND conversation_id=%s AND card_id=%s AND request_id=%s
              RETURNING request_id""",
            (request["state"], Jsonb(request["result"]),
             Jsonb(request["finish_payload"]), request["error_code"],
             Jsonb(request["card_snapshot"]), request["environment"],
             request["user_id"], request["conversation_id"], request["card_id"],
             request["request_id"])).fetchone()
        if row is None:
            _reject("CARD_STORE_OPERATION_UNCONFIRMED")

    def append_observation(
        self, scope: Scope, event_id: str, payload: JsonObject
    ) -> ObservationRow:
        self._connection.execute(
            """INSERT INTO chat_a2ui_observation_heads
              (environment,user_id,conversation_id,next_sequence)
              VALUES (%s,%s,%s,1) ON CONFLICT DO NOTHING""", scope)
        head = self._connection.execute(
            """SELECT next_sequence FROM chat_a2ui_observation_heads
              WHERE environment=%s AND user_id=%s AND conversation_id=%s
              FOR UPDATE""", scope).fetchone()
        existing = self._connection.execute(
            """SELECT sequence,event_id,payload FROM chat_a2ui_observations
              WHERE environment=%s AND user_id=%s AND conversation_id=%s
              AND event_id=%s""", (*scope, event_id)).fetchone()
        if existing is not None:
            if existing["payload"] != payload:
                _reject("CHAT_OBSERVATION_CONFLICT")
            return cast(ObservationRow, dict(existing))
        sequence = head["next_sequence"]
        self._connection.execute(
            """UPDATE chat_a2ui_observation_heads SET next_sequence=%s
              WHERE environment=%s AND user_id=%s AND conversation_id=%s""",
            (sequence + 1, *scope))
        row = self._connection.execute(
            """INSERT INTO chat_a2ui_observations
              (environment,user_id,conversation_id,sequence,event_id,payload)
              VALUES (%s,%s,%s,%s,%s,%s) RETURNING sequence,event_id,payload""",
            (*scope, sequence, event_id, Jsonb(payload))).fetchone()
        return cast(ObservationRow, dict(row))

    def list_observations(
        self, scope: Scope, after_sequence: int, limit: int
    ) -> list[ObservationRow]:
        rows = self._connection.execute(
            """SELECT sequence,event_id,payload FROM chat_a2ui_observations
              WHERE environment=%s AND user_id=%s AND conversation_id=%s
              AND sequence>%s ORDER BY sequence LIMIT %s""",
            (*scope, after_sequence, limit)).fetchall()
        return [cast(ObservationRow, dict(row)) for row in rows]
