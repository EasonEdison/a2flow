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
from typing import Protocol

from .errors import RemoteRuntimeError

_STATUS_BY_CODE = {
    "INVALID_INPUT": 400,
    "INVALID_SERVICE_INPUT": 400,
    "CONTROL_NOT_FOUND": 404,
    "RUN_NOT_FOUND": 404,
    "RESTART_SOURCE_OUTSIDE_THIS_SLICE": 409,
    "RUN_STOPPED": 409,
}


class RuntimeClient(Protocol):
    def start(self, control_request_id: str, definition_key: str,
              inputs: dict) -> dict: ...

    def control(self, control_id: str) -> dict: ...

    def stop(self, run_id: str, control_request_id: str) -> dict: ...

    def action(self, run_id: str, node_id: str, payload: dict) -> dict: ...

    def view(self, run_id: str) -> dict: ...

    def action_stream(self, run_id: str, node_id: str,
                      payload: dict) -> "object": ...

    def surface_stream(self, run_id: str) -> "object": ...


class HttpRuntimeClient:
    """Minimal JSON client over the reviewed runtime control interface."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self._base + path, data=data, method=method)
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

    def _stream(self, request):
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
