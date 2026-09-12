"""One-shot MVP08 live-chain probe. Importing this module performs no I/O."""

import asyncio
import json
import os
from pathlib import Path
import re
import socket
import threading
import time
import traceback

import httpx
from pydantic import SecretStr
from skillweave_contracts import TrustedContext

from a2flow_asset_store import PostgresAssetRepository
from activity_planning_demo import (
    application_validator,
    bundle_validator,
)
from activity_planning_demo.bundle import NAMESPACE, make_bundle
from agent_workflow_runtime.http import ERRORS
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.mvp_assembly import MvpRuntimeHost
from runtime_phase1 import runtime03_pg_window as shared
from runtime_phase1.postgres_parallel_probe import _connection_string
from runtime_phase1.runtime08_mvp_window import (
    MODEL_KEY_FILE_ENV,
    SPEC,
    verified_model_key_file,
)


LISTENER_HOST = "127.0.0.1"
LISTENER_PORT = 18765
MODEL_CALL_LIMIT = 6
MODEL_TIMEOUT_SECONDS = 20.0
MAX_OUTPUT_TOKENS_PER_CALL = 2048
START_TIMEOUT_SECONDS = 100.0
ACTION_TIMEOUT_SECONDS = 60.0
WINDOW_USER_ID = "mvp08-live-user"
WINDOW_ENVIRONMENT = "PRT"
WINDOW_DATABASE = "runtime_probe"
WINDOW_ID_PATTERN_LENGTH = 32
BACKEND_ERROR_CODES = frozenset(code for _, code in ERRORS.values()) | frozenset({
    "BODY_TOO_LARGE",
    "CAPACITY_EXHAUSTED",
    "INTERNAL_ERROR",
    "READ_TIMEOUT",
    "REPLAY_UNSUPPORTED",
    "RUNTIME_ERROR",
    "SUBSCRIBER_CAPACITY_EXHAUSTED",
})
BACKEND_DIAGNOSTIC_FRAME_LIMIT = 8
BACKEND_DIAGNOSTIC_TOKEN = re.compile(r"^[A-Za-z0-9_.<>-]{1,96}$")
PROVIDER_EXCEPTION_MODULES = ("httpx", "openai", "langchain_deepseek")
PROVIDER_EXCEPTION_TYPES = frozenset({"DeepSeekProtocolError"})


class SafeHttpFailure(RuntimeError):
    """Retain only bounded HTTP metadata, never the response or its body."""

    def __init__(self, kind, status, response_json, error_code=None):
        super().__init__("MVP08_HTTP_RESPONSE_FAILED")
        self.evidence = {
            "failureKind": kind,
            "failureSite": "assert_status",
            "httpStatus": status,
            "responseJson": response_json,
        }
        if error_code is not None:
            self.evidence["errorCode"] = error_code


class ModelRequestBudgetGuard(RuntimeError):
    """A seventh request was rejected locally before network dispatch."""


def _exception_chain(error):
    observed = set()
    while isinstance(error, BaseException) and id(error) not in observed:
        observed.add(id(error))
        yield error
        error = error.__cause__ or error.__context__


def _backend_diagnostic(error):
    chain = tuple(_exception_chain(error))
    selected = chain[0]
    category = "BACKEND_EXCEPTION"
    for candidate in chain:
        if isinstance(candidate, ModelRequestBudgetGuard):
            selected = candidate
            category = "MODEL_REQUEST_BUDGET_GUARD"
            break
    else:
        prefixes = tuple(item + "." for item in PROVIDER_EXCEPTION_MODULES)
        for candidate in chain:
            module = type(candidate).__module__
            if (module in PROVIDER_EXCEPTION_MODULES or module.startswith(prefixes)
                    or type(candidate).__name__ in PROVIDER_EXCEPTION_TYPES):
                selected = candidate
                category = "PROVIDER_OR_SDK_EXCEPTION"
                break
    exception_type = type(selected).__name__
    if not BACKEND_DIAGNOSTIC_TOKEN.fullmatch(exception_type):
        exception_type = "UNKNOWN_EXCEPTION"
    frames = []
    for frame in traceback.extract_tb(selected.__traceback__)[-BACKEND_DIAGNOSTIC_FRAME_LIMIT:]:
        filename = Path(frame.filename).name
        function = frame.name
        if (BACKEND_DIAGNOSTIC_TOKEN.fullmatch(filename)
                and BACKEND_DIAGNOSTIC_TOKEN.fullmatch(function)):
            frames.append(f"{filename}:{frame.lineno}:{function}")
    return {
        "backendCategory": category,
        "backendExceptionType": exception_type,
        "backendStackFrames": frames,
    }


def observe_backend_failure(error):
    """Persist a bounded private diagnostic without changing the public response."""
    try:
        shared.append_evidence(
            "BACKEND_FAILURE", window=SPEC, **_backend_diagnostic(error),
        )
    except Exception:
        pass


class RequestBudget:
    """Bound exact DeepSeek chat requests before network dispatch."""

    def __init__(self):
        self._lock = threading.Lock()
        self._calls = 0

    @property
    def calls(self):
        with self._lock:
            return self._calls

    def admit(self, request, body):
        if (request.method != "POST" or request.url.scheme != "https"
                or request.url.host != "api.deepseek.com"
                or request.url.port not in (None, 443)
                or not request.url.path.endswith("/chat/completions")):
            raise RuntimeError("UNEXPECTED_PROVIDER_DESTINATION")
        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            raise RuntimeError("INVALID_PROVIDER_REQUEST") from None
        if (payload.get("model") != "deepseek-v4-flash"
                or payload.get("max_tokens") != MAX_OUTPUT_TOKENS_PER_CALL
                or type(payload.get("stream")) is not bool):
            raise RuntimeError("MODEL_BUDGET_NOT_APPLIED")
        with self._lock:
            if self._calls >= MODEL_CALL_LIMIT:
                raise ModelRequestBudgetGuard("MODEL_CALL_LIMIT_EXCEEDED")
            self._calls += 1


class SyncBudgetTransport(httpx.BaseTransport):
    def __init__(self, budget):
        self.budget = budget
        self.inner = httpx.HTTPTransport(retries=0)

    def handle_request(self, request):
        self.budget.admit(request, request.read())
        return self.inner.handle_request(request)

    def close(self):
        self.inner.close()


class AsyncBudgetTransport(httpx.AsyncBaseTransport):
    def __init__(self, budget):
        self.budget = budget
        self.inner = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        self.budget.admit(request, await request.aread())
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        await self.inner.aclose()


class WindowModelFactory:
    def __init__(self, owner, key, budget):
        self.owner = owner
        self.key = key
        self.budget = budget

    def configuration(self, reference, owner):
        if reference != "deepseek-v4-flash" or owner != self.owner:
            raise RuntimeError("MODEL_CONFIGURATION_NOT_FOUND")
        return {
            "model_id": "deepseek-v4-flash",
            "credential_ref": "window:file",
            "timeout_seconds": MODEL_TIMEOUT_SECONDS,
            "options": {
                "thinking": "enabled",
                "reasoning_effort": "low",
                "max_tokens": MAX_OUTPUT_TOKENS_PER_CALL,
            },
        }

    def secret(self, reference, owner):
        if reference != "window:file" or owner != self.owner:
            raise RuntimeError("MODEL_CREDENTIAL_UNAVAILABLE")
        return SecretStr(self.key)

    def create(self, reference, owner):
        sync_client = httpx.Client(transport=SyncBudgetTransport(self.budget))
        async_client = httpx.AsyncClient(transport=AsyncBudgetTransport(self.budget))
        factory = DeepSeekModelFactory(
            self.configuration,
            self.secret,
            http_client=sync_client,
            http_async_client=async_client,
        )
        try:
            return factory.create(reference, owner)
        except Exception:
            sync_client.close()
            asyncio.run(async_client.aclose())
            raise


def read_model_key():
    path = verified_model_key_file()
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = stream.read(513)
    except OSError:
        raise RuntimeError("MODEL_KEY_FILE_UNAVAILABLE") from None
    value = value.rstrip("\r\n")
    if not value or len(value) > 512 or any(character.isspace() for character in value):
        raise RuntimeError("MODEL_KEY_FILE_INVALID")
    return value


def environment_value(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MVP08_WINDOW_ENV_REQUIRED")
    return value


def assert_listener_available():
    candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        candidate.bind((LISTENER_HOST, LISTENER_PORT))
    except OSError:
        raise RuntimeError("LOOPBACK_PORT_UNAVAILABLE") from None
    finally:
        candidate.close()


def assert_status(response, expected=200):
    try:
        payload = response.json()
    except ValueError:
        raise SafeHttpFailure(
            "HTTP_STATUS" if response.status_code != expected else "HTTP_NON_JSON",
            response.status_code,
            False,
        ) from None
    if response.status_code != expected:
        candidate = None
        if type(payload) is dict and type(payload.get("error")) is dict:
            candidate = payload["error"].get("code")
        raise SafeHttpFailure(
            "HTTP_STATUS",
            response.status_code,
            True,
            candidate if type(candidate) is str and candidate in BACKEND_ERROR_CODES else None,
        )
    if type(payload) is not dict:
        raise SafeHttpFailure("HTTP_JSON_SHAPE", response.status_code, True)
    return payload


def seed_assets(conninfo):
    validator = bundle_validator()
    repository = PostgresAssetRepository(
        conninfo,
        environment=WINDOW_ENVIRONMENT,
        database=WINDOW_DATABASE,
        validator=validator,
    )
    document = make_bundle(WINDOW_ENVIRONMENT)
    repository.setup()
    dry_run = repository.import_bundle(
        document,
        expected_namespace=NAMESPACE,
        dry_run=True,
    )
    if dry_run["status"] != "WOULD_INSERT" or len(dry_run["assets"]) != 7:
        raise RuntimeError("ASSET_DRY_RUN_MISMATCH")
    applied = repository.import_bundle(
        document,
        expected_namespace=NAMESPACE,
        dry_run=False,
    )
    observed = repository.read(NAMESPACE)
    if applied["status"] != "INSERTED" or len(observed.assets) != 7:
        raise RuntimeError("ASSET_READBACK_MISMATCH")
    return len(observed.assets)


def waiting_card(client, run_id):
    view = assert_status(client.get(f"/runtime/runs/{run_id}/view"))
    cards = view.get("cards")
    if (view.get("lifecycle") != "RUNNING" or type(cards) is not list
            or len(cards) != 1 or cards[0].get("state") != "WAITING"
            or cards[0].get("actionEligibility") != "REVALIDATION_REQUIRED"):
        raise RuntimeError("WAITING_CARD_NOT_OBSERVED")
    card = cards[0]
    options = card.get("data", {}).get("options")
    if type(options) is not list or len(options) < 2:
        raise RuntimeError("WAITING_OPTIONS_NOT_OBSERVED")
    option = options[0]
    if (type(option) is not dict or type(option.get("value")) is not str
            or not option["value"]):
        raise RuntimeError("WAITING_OPTION_INVALID")
    return card, option["value"]


def assert_completed(view, selected_option):
    if view.get("lifecycle") != "SUCCEEDED":
        raise RuntimeError("RUN_NOT_SUCCEEDED")
    nodes = view.get("nodes")
    if (type(nodes) is not list or
            [(node.get("nodeId"), node.get("status")) for node in nodes]
            != [("plan", "SUCCEEDED"), ("copy", "SUCCEEDED")]):
        raise RuntimeError("NODE_RESULTS_INCOMPLETE")
    outputs = view.get("outputs")
    if type(outputs) is not list:
        raise RuntimeError("OUTPUTS_UNAVAILABLE")
    selected = [
        item for item in outputs
        if item.get("kind") == "ACTION_RESULT"
        and item.get("content", {}).get("selectedOptionId") == selected_option
    ]
    copy = [
        item for item in outputs
        if item.get("nodeId") == "copy" and item.get("kind") == "MODEL_TEXT"
        and type(item.get("content")) is str and item["content"]
    ]
    if len(selected) != 1 or len(copy) != 1:
        raise RuntimeError("FINAL_OUTPUTS_INCOMPLETE")


def _execute(progress):
    progress["stage"] = "WINDOW_CONTEXT"
    marker = environment_value("A2FLOW_MVP08_WINDOW_ID")
    if len(marker) != WINDOW_ID_PATTERN_LENGTH or any(
            character not in "0123456789abcdef" for character in marker):
        raise RuntimeError("MVP08_WINDOW_MARKER_INVALID")
    socket_directory = Path(environment_value("A2FLOW_MVP08_SOCKET"))
    password_file = Path(environment_value("A2FLOW_MVP08_PASSWORD_FILE"))
    progress["stage"] = "MODEL_KEY_READ"
    model_key = read_model_key()
    conninfo = _connection_string(socket_directory, password_file)
    owner = TrustedContext.from_mapping({
        "userId": WINDOW_USER_ID,
        "environment": WINDOW_ENVIRONMENT,
    })

    os.environ.update({
        "A2FLOW_DATABASE_URL": conninfo,
        "A2FLOW_DATABASE_NAME": WINDOW_DATABASE,
        "A2FLOW_ENVIRONMENT": WINDOW_ENVIRONMENT,
        "A2FLOW_USER_ID": WINDOW_USER_ID,
    })
    from deploy.mvp import app as deployment

    progress["stage"] = "ASSET_SEED"
    asset_count = seed_assets(conninfo)
    shared.append_evidence(
        "LIVE_STAGE", window=SPEC, phase="ASSETS_SEEDED", assetCount=asset_count,
    )
    budget = RequestBudget()
    progress["budget"] = budget
    progress["stage"] = "RUNTIME_HOST"
    import uvicorn
    host = MvpRuntimeHost(
        conninfo=conninfo,
        database=WINDOW_DATABASE,
        environment=WINDOW_ENVIRONMENT,
        namespace=NAMESPACE,
        bundle_validator=bundle_validator(),
        application_validator=application_validator,
        operation_specs=deployment.operations(),
        model_factory=WindowModelFactory(owner, model_key, budget),
        identity_resolver=lambda scope: owner,
        unexpected_error_observer=observe_backend_failure,
    )
    progress["stage"] = "LISTENER_START"
    assert_listener_available()
    config = uvicorn.Config(
        host.create_app(),
        host=LISTENER_HOST,
        port=LISTENER_PORT,
        log_level="critical",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="mvp08-loopback", daemon=False)
    started = time.monotonic()
    thread.start()
    try:
        base_url = f"http://{LISTENER_HOST}:{LISTENER_PORT}"
        with httpx.Client(base_url=base_url) as client:
            progress["operation"] = "SESSION_READ"
            deadline = time.monotonic() + 10
            while True:
                try:
                    session = assert_status(client.get("/runtime/session", timeout=1))
                    break
                except (httpx.TransportError, RuntimeError):
                    if time.monotonic() >= deadline or not thread.is_alive():
                        raise RuntimeError("LOOPBACK_LISTENER_NOT_READY") from None
                    time.sleep(.1)
            if session != {"userId": WINDOW_USER_ID, "environment": WINDOW_ENVIRONMENT}:
                raise RuntimeError("SESSION_IDENTITY_MISMATCH")
            progress["stage"] = "START_REQUEST"
            progress["operation"] = "START_RUN"
            shared.append_evidence(
                "LIVE_STAGE", window=SPEC, phase="LISTENER_READY", modelCalls=budget.calls,
            )
            start = assert_status(client.post(
                "/runtime/runs",
                json={
                    "controlRequestId": "mvp08.live.start.001",
                    "definitionKey": "activity-planning",
                    "inputs": {
                        "requirement": (
                            "为12人团队策划一次周五晚餐，预算120000分。"
                            "给出两个可比较方案，等待我确认后再写一份邀请文案。"
                        ),
                    },
                },
                timeout=START_TIMEOUT_SECONDS,
            ))
            run_id = start.get("runId")
            if type(run_id) is not str or not run_id:
                raise RuntimeError("RUN_ID_UNAVAILABLE")
            progress["stage"] = "WAITING_CARD"
            progress["operation"] = "WAITING_VIEW"
            shared.append_evidence(
                "LIVE_STAGE", window=SPEC, phase="START_RETURNED", modelCalls=budget.calls,
            )
            card, selected_option = waiting_card(client, run_id)
            progress["stage"] = "ACTION_REQUEST"
            progress["operation"] = "ACTION_SUBMIT"
            shared.append_evidence(
                "LIVE_STAGE", window=SPEC, phase="CARD_OBSERVED", modelCalls=budget.calls,
                cardObserved=True,
            )
            assert_status(client.post(
                f"/runtime/runs/{run_id}/nodes/plan/actions",
                json={
                    "interactionId": card["interactionId"],
                    "actionName": "confirm_activity",
                    "controlRequestId": "mvp08.live.confirm.001",
                    "inputs": {"optionId": selected_option, "confirmed": True},
                },
                timeout=ACTION_TIMEOUT_SECONDS,
            ))
            progress["stage"] = "FINAL_VIEW_READ"
            progress["operation"] = "FINAL_VIEW"
            shared.append_evidence(
                "LIVE_STAGE", window=SPEC, phase="ACTION_RETURNED", modelCalls=budget.calls,
            )
            final_view = assert_status(client.get(f"/runtime/runs/{run_id}/view"))
            progress["stage"] = "FINAL_VIEW_VALIDATE"
            assert_completed(final_view, selected_option)
        if not 1 <= budget.calls <= MODEL_CALL_LIMIT:
            raise RuntimeError("MODEL_CALL_COUNT_INVALID")
        return {
            "status": "PASS",
            "assetCount": asset_count,
            "listener": f"{LISTENER_HOST}:{LISTENER_PORT}",
            "modelCalls": budget.calls,
            "modelCallLimit": MODEL_CALL_LIMIT,
            "maxOutputTokensPerCall": MAX_OUTPUT_TOKENS_PER_CALL,
            "maxOutputTokensTotal": MODEL_CALL_LIMIT * MAX_OUTPUT_TOKENS_PER_CALL,
            "modelTimeoutSeconds": MODEL_TIMEOUT_SECONDS,
            "elapsedSeconds": round(time.monotonic() - started, 2),
            "lifecycle": "SUCCEEDED",
            "nodeStatuses": ["SUCCEEDED", "SUCCEEDED"],
        }
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        if thread.is_alive():
            raise RuntimeError("LOOPBACK_LISTENER_RESIDUAL")


def _run():
    progress = {"stage": "INITIAL", "operation": "WINDOW_SETUP", "budget": None}
    try:
        evidence = _execute(progress)
    except Exception as error:
        budget = progress["budget"]
        details = {}
        if isinstance(error, SafeHttpFailure):
            details.update(error.evidence)
        elif isinstance(error, httpx.TimeoutException):
            details["failureKind"] = "HTTP_TIMEOUT"
        elif isinstance(error, httpx.TransportError):
            details["failureKind"] = "HTTP_TRANSPORT"
        else:
            details["failureKind"] = "HOST_EXCEPTION"
        try:
            shared.append_evidence(
                "LIVE_RESULT", window=SPEC, outcome="FAILED",
                errorStage=progress["stage"], errorType=type(error).__name__,
                modelCalls=budget.calls if budget is not None else 0,
                operation=progress["operation"], **details,
            )
        except Exception:
            pass
        raise RuntimeError("MVP08_LIVE_CHAIN_FAILED") from None
    shared.append_evidence(
        "LIVE_RESULT", window=SPEC, outcome="PASS",
        assetCount=evidence["assetCount"], cardObserved=True,
        modelCalls=evidence["modelCalls"], lifecycle=evidence["lifecycle"],
        nodeStatuses=evidence["nodeStatuses"],
    )
    return evidence


def run():
    evidence = _run()
    print(json.dumps(evidence, sort_keys=True), flush=True)
    return evidence
