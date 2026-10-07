"""HTTP client for the Runtime control interface (v1 proxy, stdlib only).

The b-side service never imports Runtime internals; it talks to the reviewed
control routes. Delivery is proxied verbatim; ownership is enforced by the
b-side run_ownership table before any call is forwarded.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Protocol
from skillweave_contracts.user_id import require_user_id, user_id_to_wire

from .errors import RemoteRuntimeError

_STATUS_BY_CODE = {
    "CAPACITY_EXHAUSTED": 503,
    "INVALID_INPUT": 400,
    "INVALID_SERVICE_INPUT": 400,
    "CONTROL_NOT_FOUND": 404,
    "RUN_NOT_FOUND": 404,
    "RESTART_SOURCE_OUTSIDE_THIS_SLICE": 409,
    "RUN_STOPPED": 409,
}


class RuntimeClient(Protocol):
    def for_user(self, user_id: int, environment: str) -> "RuntimeClient": ...

    def start(self, control_request_id: str, definition_key: str,
              inputs: dict) -> dict: ...

    def control(self, control_id: str) -> dict: ...

    def stop(self, run_id: str, control_request_id: str) -> dict: ...

    def action(self, run_id: str, node_id: str, payload: dict) -> dict: ...

    def view(self, run_id: str) -> dict: ...

    def cards(self, run_id: str) -> dict[str, object]: ...

    def card_action(
        self, run_id: str, card_id: str, payload: dict[str, object],
    ) -> dict[str, object]: ...

    def resume_card(
        self, run_id: str, card_id: str, payload: dict[str, object],
    ) -> dict[str, object]: ...

    def resume_status(
        self, run_id: str, card_id: str, query: dict[str, str],
    ) -> dict[str, object]: ...

    def action_stream(self, run_id: str, node_id: str,
                      payload: dict) -> "object": ...

    def surface_stream(self, run_id: str) -> "object": ...

    def progress_catalog(self, run_id: str, query: list[tuple[str, str]]) -> dict[str, object]: ...

    def progress_history(
        self, run_id: str, node_id: str, execution_id: str, query: list[tuple[str, str]],
    ) -> dict[str, object]: ...

    def progress_stream(
        self, run_id: str, node_id: str, execution_id: str,
        query: list[tuple[str, str]], last_event_id: str | None,
    ) -> Iterator[str]: ...


class HttpRuntimeClient:
    """Minimal JSON client over the reviewed runtime control interface."""

    def __init__(self, base_url: str, timeout: float = 10.0, *,
                 user_id: int | None = None, environment: str | None = None):
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._user_id = require_user_id(user_id) if user_id is not None else None
        self._environment = environment

    def for_user(self, user_id: int, environment: str) -> "HttpRuntimeClient":
        # A new client per invocation: never mutate a shared client's identity.
        require_user_id(user_id)
        if environment not in {"PRT", "ONLINE"}:
            raise ValueError("TRUSTED_CONTEXT_REQUIRED")
        return HttpRuntimeClient(self._base, self._timeout,
                                 user_id=user_id, environment=environment)

    def _identify(self, request):
        if self._user_id is None or self._environment is None:
            raise ValueError("TRUSTED_CONTEXT_REQUIRED")
        request.add_header("X-A2Flow-User-Id", user_id_to_wire(self._user_id))
        request.add_header("X-A2Flow-Environment", self._environment)

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self._base + path, data=data, method=method)
        self._identify(request)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request,
                                        timeout=self._timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            code = "RUNTIME_REJECTED"
            try:
                payload = json.load(error)
                code = payload.get("error", {}).get("code", code)
            except Exception:
                pass
            status = _STATUS_BY_CODE.get(code, 502)
            raise RemoteRuntimeError(code, status) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RemoteRuntimeError("RUNTIME_UNREACHABLE", 502) from None

    def start(self, control_request_id: str, definition_key: str,
              inputs: dict) -> dict:
        return self._request("POST", "/runtime/runs", {
            "controlRequestId": control_request_id,
            "definitionKey": definition_key,
            "inputs": inputs,
        })

    def control(self, control_id: str) -> dict:
        quoted = urllib.parse.quote(control_id, safe="")
        return self._request("GET", "/runtime/controls/" + quoted)

    def view(self, run_id: str) -> dict:
        quoted = urllib.parse.quote(run_id, safe="")
        return self._request("GET", "/runtime/runs/" + quoted + "/view")

    def cards(self, run_id: str) -> dict[str, object]:
        return self._request(
            "GET", "/runtime/runs/" + urllib.parse.quote(run_id, safe="") + "/cards",
        )

    def card_action(
        self, run_id: str, card_id: str, payload: dict[str, object],
    ) -> dict[str, object]:
        return self._request(
            "POST", "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/cards/" + urllib.parse.quote(card_id, safe="") + "/actions", payload,
        )

    def resume_card(
        self, run_id: str, card_id: str, payload: dict[str, object],
    ) -> dict[str, object]:
        return self._request(
            "POST", "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/cards/" + urllib.parse.quote(card_id, safe="") + "/resume", payload,
        )

    def resume_status(
        self, run_id: str, card_id: str, query: dict[str, str],
    ) -> dict[str, object]:
        return self._request(
            "GET", "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/cards/" + urllib.parse.quote(card_id, safe="") + "/resume-status?"
            + urllib.parse.urlencode(query),
        )

    def action_stream(self, run_id: str, node_id: str, payload: dict):
        """POST the action and yield the runtime SSE chunks verbatim."""
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._base + "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/nodes/" + urllib.parse.quote(node_id, safe="") + "/actions",
            data=data, method="POST")
        request.add_header("Accept", "text/event-stream")
        request.add_header("Content-Type", "application/json")
        return self._stream(request)

    def surface_stream(self, run_id: str):
        """Subscribe to snapshot + surface updates for one run."""
        request = urllib.request.Request(
            self._base + "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/surface")
        request.add_header("Accept", "text/event-stream")
        return self._stream(request)

    @staticmethod
    def _progress_path(run_id: str, node_id: str, execution_id: str) -> str:
        quote = urllib.parse.quote
        return ("/runtime/runs/" + quote(run_id, safe="")
                + "/nodes/" + quote(node_id, safe="")
                + "/executions/" + quote(execution_id, safe=""))

    def progress_catalog(self, run_id: str, query: list[tuple[str, str]]) -> dict[str, object]:
        return self._request(
            "GET", "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/progress?" + urllib.parse.urlencode(query),
        )

    def progress_history(
        self, run_id: str, node_id: str, execution_id: str, query: list[tuple[str, str]],
    ) -> dict[str, object]:
        return self._request(
            "GET", self._progress_path(run_id, node_id, execution_id)
            + "/history?" + urllib.parse.urlencode(query),
        )

    def progress_stream(
        self, run_id: str, node_id: str, execution_id: str,
        query: list[tuple[str, str]], last_event_id: str | None,
    ) -> Iterator[str]:
        request = urllib.request.Request(
            self._base + self._progress_path(run_id, node_id, execution_id)
            + "/stream?" + urllib.parse.urlencode(query),
        )
        request.add_header("Accept", "text/event-stream")
        if last_event_id is not None:
            request.add_header("Last-Event-ID", last_event_id)
        return self._stream(request)

    def _stream(self, request: urllib.request.Request) -> Iterator[str]:
        self._identify(request)
        try:
            response = urllib.request.urlopen(request, timeout=180.0)
        except urllib.error.HTTPError as error:
            self._raise_http_error(error)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RemoteRuntimeError("RUNTIME_UNREACHABLE", 502) from None

        def chunks():
            try:
                for raw in response:
                    yield raw.decode("utf-8")
            finally:
                response.close()
        return chunks()

    def _raise_http_error(self, error):
        code = "RUNTIME_REJECTED"
        try:
            payload = json.load(error)
            code = payload.get("error", {}).get("code", code)
        except Exception:
            pass
        status = _STATUS_BY_CODE.get(code, 502)
        raise RemoteRuntimeError(code, status) from None

    def stop(self, run_id: str, control_request_id: str) -> dict:
        return self._request(
            "POST",
            "/runtime/runs/" + urllib.parse.quote(run_id, safe="") + "/stop",
            {"controlRequestId": control_request_id})

    def action(self, run_id: str, node_id: str, payload: dict) -> dict:
        return self._request(
            "POST",
            "/runtime/runs/" + urllib.parse.quote(run_id, safe="")
            + "/nodes/" + urllib.parse.quote(node_id, safe="") + "/actions",
            payload)
