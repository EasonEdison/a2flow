#!/usr/bin/env python3
"""Offline confirmation probe: synthetic owners, in-memory cards, no business transport.

Run with the runtime dependencies installed. The existing test-only card storage
fixture supplies transactions; no test suite or real database is started.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from threading import RLock
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for relative in ("packages/contracts/src", "packages/asset-store/src", "services/b-side-api/src",
                 "services/agent-workflow-runtime/src", "services/skill-registry/src",
                 "services/capability-registry/src", "services/a2ui-composer/src",
                 "services/agent-workflow-runtime/tests"):
    sys.path.insert(0, str(ROOT / relative))

from skillweave_contracts import TrustedContext
from agent_workflow_runtime.capability_approval import receipt_for
from agent_workflow_runtime.temporary_interaction import completed_interaction
from agent_workflow_runtime.chat.cards import ChatCardStore
from agent_workflow_runtime.chat.rpc_actions import RpcChatActionService
from agent_workflow_runtime.chat.rpc_assets import RpcChatAssets
from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.rpc_client import AbilityDescription
from a2flow_bside.processing_tasks import ProcessingTasksRepository
from test_chat_cards import MemoryStorage

checks = 0
OWNER = TrustedContext(9123401, "PRT")
ARGUMENTS = {"title": "synthetic confirmation probe"}


def check(condition):
    global checks
    if not condition:
        raise AssertionError("confirmation probe invariant failed")
    checks += 1


def rejected(call, code=None):
    try:
        call()
    except ActionRejected as error:
        check(code is None or error.code == code)
    else:
        raise AssertionError("expected rejection")


class Rpc:
    def __init__(self, level="WRITE", fail=False):
        self.calls = []
        self.fail = fail
        self.description = AbilityDescription("asset", "demo.write", 1, "synthetic", {}, [],
            "PRT", "source", "digest", level,
            "AUTO_EXECUTE" if level == "READ" else "REQUEST_APPROVAL")

    def resolve(self, *args):
        return self.description

    def execute(self, owner, asset, arguments, request_id, **kwargs):
        self.calls.append((owner, asset, copy.deepcopy(arguments), kwargs))
        if self.fail:
            raise TimeoutError("synthetic unknown transport outcome")
        if self.description.side_effect_level != "READ":
            check(kwargs["approval_receipt"]["user_id"] == OWNER.user_id)
            check(kwargs["approval_receipt"]["arguments_digest"] == hashlib.sha256(
                json.dumps(arguments, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode()).hexdigest())
        return SimpleNamespace(success=True, data={"recordId": "synthetic-result"},
            error_code="", request_id=request_id, action_code="demo.write", capability_version=1,
            resolved_environment="PRT", source_id="source", source_digest="digest")


def fixture(level="WRITE", fail=False):
    memory = MemoryStorage()
    store = ChatCardStore(None, environment="PRT", _storage=memory)
    rpc = Rpc(level, fail)
    assets = object.__new__(RpcChatAssets)
    assets._owner, assets._conversation_id, assets._control_request_id = OWNER, "731", "turn:41"
    assets.rpc = rpc
    assets._processing_context = assets._processing_provider = assets._processing_turn_id = None
    assets._admission = SimpleNamespace(skill_key="skill")
    assets._record = lambda *args: {"definition": {"assetKey": "asset"}, "versionId": "v1"}
    assets._render_lock, assets._waiting_action = RLock(), None
    assets._render_observations = {}
    assets._card_sink = lambda prepared, metadata: store.save(OWNER, "731", prepared, metadata)
    assets.admit_skill = lambda key: check(key == "skill")
    factory_calls = []

    def factory(*args, **kwargs):
        factory_calls.append((args, kwargs))
        return assets

    return assets, rpc, store, memory, RpcChatActionService(store, factory), factory_calls


def submit(service, card, owner=OWNER, request="request-1", inputs=None):
    return service.execute(owner, "731", card["cardId"], request_id=request,
                           action_name="submit", inputs=inputs or {"confirmation": ["approve"]})


def a2ui_probe():
    from dataclasses import asdict
    from agent_workflow_runtime.application_runtime import PreparedApplication
    from agent_workflow_runtime.rpc_client import ReleaseIdentity, RuntimeSession

    def fixture(*, level="WRITE", workflow=False, completes=True, fail=False):
        memory = MemoryStorage()
        store = ChatCardStore(None, environment="PRT", _storage=memory)
        display = {"protocolProfile": "a2flow.java-rpc.v1", "applicationKey": "app",
                   "applicationVersion": "v1", "snapshotMessages": [], "data": {}, "components": [],
                   "actions": [{"surfaceId": "main", "componentId": "save", "actionName": "save",
                                "inputSchema": {"type": "object"}}]}
        release = ReleaseIdentity("app", "source", "digest", "v1", "PRT")
        session = RuntimeSession("synthetic-session", "v1", "v0.9.1", "catalog", "1", "catalog-digest")
        metadata = {"skillKey": "skill", "conversationId": "731", "controlRequestId": "turn:41",
                    "toolCallId": "render", "applicationKey": "app", "applicationVersion": "v1",
                    "rpc": {"release": asdict(release), "session": asdict(session), "params": {}}}
        if workflow:
            metadata["workflow"] = {"runId": "synthetic-run", "nodeId": "synthetic-node"}
        card = store.save(OWNER, "731", PreparedApplication("app", "v1", True, json.dumps(display)), metadata)
        description = Rpc(level).description
        catalog = SimpleNamespace(protocol_version="v0.9.1", catalog_id="catalog", catalog_revision="1",
                                  catalog_digest="catalog-digest")
        action = SimpleNamespace(action_name="save", surface_id="main", component_id="save",
                                 context_schema={"type": "object"})

        class A2uiRpc:
            def __init__(self):
                self.preflights, self.calls = [], []

            def prepare_action(self, owner, trusted, action_message, request_id, **kwargs):
                self.preflights.append(request_id)
                check(trusted.app_code == "app" and action_message["action"]["name"] == "save")
                return SimpleNamespace(description=description, arguments=copy.deepcopy(ARGUMENTS), binding_id="save")

            def act(self, owner, trusted, action_message, request_id, **kwargs):
                self.calls.append(kwargs)
                check(trusted.app_code == "app" and action_message["action"]["context"] == ARGUMENTS)
                if level == "WRITE":
                    receipt = kwargs["approval_receipt"]
                    check(receipt["source_digest"] == "digest" and receipt["action_code"] == "demo.write")
                    check(receipt["arguments_digest"] == hashlib.sha256(json.dumps(ARGUMENTS,
                        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
                    check(receipt["run_id"] == ("synthetic-run" if workflow else "731"))
                if fail:
                    raise TimeoutError("synthetic unknown")
                observed = SimpleNamespace(action_code="demo.write", arguments=ARGUMENTS,
                    result={"recordId": "synthetic-ui-result"}, capability_success=True, business_success=True,
                    presentation_error_code=None, capability_error_code=None)
                return SimpleNamespace(release=release, session=session, params={}, executions=(),
                    generated_definition=None, snapshot=(), catalog=catalog, actions=() if completes else (action,),
                    interaction_mode="DISPLAY_ONLY" if completes else "INTERACTIVE", business_success=True,
                    complete_interaction=completes, action_observation=observed, composer_draft_effects=())

        rpc = A2uiRpc()
        assets = SimpleNamespace(rpc=rpc, admit_skill=lambda key: check(key == "skill"),
            action_descriptions=lambda: {"demo.write": "synthetic write"},
            application_description=lambda key: ({}, SimpleNamespace(actions=(action,), catalog=catalog)))
        service = RpcChatActionService(store, lambda *args, **kwargs: assets)
        return store, card, rpc, service

    def click(service, card, request="start"):
        return service.execute(OWNER, "731", card["cardId"], request_id=request, action_name="save",
            inputs={"surfaceId": "main", "sourceComponentId": "save", "context": ARGUMENTS})

    store, card, rpc, service = fixture(level="READ")
    result = click(service, card)
    check(len(rpc.preflights) == 1 and len(rpc.calls) == 1)
    check(result["card"]["display"]["protocolProfile"] == "a2flow.java-rpc.v1")

    store, card, rpc, service = fixture()
    pending = click(service, card)
    check(pending["card"]["cardId"] == card["cardId"] and not rpc.calls)
    check(pending["card"]["status"] == "WAITING_ACTION" and "continuation" not in pending)
    check("synthetic-session" not in json.dumps(pending))
    rejected(lambda: store.get_approval_origin(TrustedContext(9123402, "PRT"), "731", card["cardId"]),
             "CARD_NOT_FOUND")
    check(pending["card"]["display"]["protocolProfile"] == "a2flow.temporary.v1")
    check(click(service, card) == pending and len(rpc.preflights) == 1)
    rejected(lambda: submit(service, card, inputs={"confirmation": []}))
    rejected(lambda: store.submit_interaction(OWNER, "731", card["cardId"], "bypass", "submit",
        {"confirmation": ["approve"]}), "WRITE_CONFIRMATION_DISPATCH_REQUIRED")
    finished = submit(service, card)
    check(len(rpc.calls) == 1 and finished["card"]["cardId"] == card["cardId"])
    check(finished["card"]["display"]["protocolProfile"] == "a2flow.java-rpc.v1")
    check(finished["card"]["status"] == "COMPLETED" and finished["continuation"]["kind"] == "WRITE_APPROVAL")
    check(submit(service, card) == finished and len(rpc.calls) == 1)
    metadata = store.get_binding(OWNER, "731", card["cardId"])["metadata"]
    check("approval" not in metadata and metadata["completedApproval"]["confirmationRequestId"] == "request-1")

    store, card, rpc, service = fixture(workflow=True)
    click(service, card)
    rejected(lambda: store.submit_interaction(OWNER, "731", card["cardId"], "bypass", "submit",
        {"confirmation": ["approve"]}), "WRITE_CONFIRMATION_DISPATCH_REQUIRED")
    completed = submit(service, card)
    metadata = store.get_binding(OWNER, "731", card["cardId"])["metadata"]
    check(metadata["workflow"] == {"runId": "synthetic-run", "nodeId": "synthetic-node"})
    check(metadata["workflowCompletionRequestId"] == "request-1")
    check(completed["card"]["status"] == "COMPLETED" and "continuation" not in completed)

    # A reusable application card must create an independent receipt for each
    # explicit new save, but never execute the same confirmation twice.
    store, card, rpc, service = fixture(completes=False)
    click(service, card, "first-save")
    first = submit(service, card, request="first-confirm")
    check(first["card"]["status"] == "WAITING_ACTION" and len(rpc.calls) == 1)
    click(service, card, "second-save")
    second = submit(service, card, request="second-confirm")
    check(second["card"]["status"] == "WAITING_ACTION" and len(rpc.calls) == 2)
    check(rpc.calls[0]["approval_receipt"]["receipt_id"] != rpc.calls[1]["approval_receipt"]["receipt_id"])
    check(rpc.calls[0]["approval_receipt"]["tool_call_id"] != rpc.calls[1]["approval_receipt"]["tool_call_id"])
    check(submit(service, card, request="second-confirm") == second and len(rpc.calls) == 2)

    store, card, rpc, service = fixture(fail=True)
    click(service, card)
    rejected(lambda: submit(service, card), "ACTION_OUTCOME_UNKNOWN")
    rejected(lambda: submit(service, card), "ACTION_OUTCOME_UNKNOWN")
    check(len(rpc.calls) == 1 and store.read(OWNER, "731", card["cardId"])["status"] == "UNKNOWN")


def main():
    assets, rpc, store, memory, service, factory = fixture("READ")
    read = assets.execute_ability("ability", ARGUMENTS, tool_call_id="tool-read")
    check(read["output"]["recordId"] == "synthetic-result" and len(rpc.calls) == 1)
    check(not memory.cards)

    assets, rpc, store, memory, service, factory = fixture()
    value = assets.execute_ability("ability", ARGUMENTS, tool_call_id="tool-write")
    card = value["approvalCard"]
    check(value["output"]["status"] == "AWAITING_APPROVAL" and not rpc.calls)
    check(card["status"] == "WAITING_ACTION" and "approval" not in card)
    check(assets.prepare_approval("ability", ARGUMENTS, "tool-write") == card)
    rejected(lambda: assets.prepare_approval("ability", {"title": "changed"}, "tool-write"),
             "WRITE_CONFIRMATION_BINDING_INVALID")
    rejected(lambda: assets.prepare_approval("ability", ARGUMENTS, "other-tool"), "INTERACTION_REQUIRED")
    check(assets.render_observation(card["cardId"])["applicationKey"] == card["display"]["applicationKey"])
    rejected(lambda: submit(service, card, inputs={"confirmation": []}))
    rejected(lambda: submit(service, card, owner=TrustedContext(9123402, "PRT")), "CARD_NOT_FOUND")
    rejected(lambda: store.submit_interaction(OWNER, "731", card["cardId"], "bypass", "submit",
                                              {"confirmation": ["approve"]}),
             "WRITE_CONFIRMATION_DISPATCH_REQUIRED")
    check(not rpc.calls)
    binding = store.get_binding(OWNER, "731", card["cardId"])["metadata"]["approval"]
    tampered = copy.deepcopy(binding)
    tampered["arguments"]["title"] = "different"
    rejected(lambda: receipt_for(OWNER, card["cardId"], tampered), "WRITE_CONFIRMATION_BINDING_INVALID")
    completed = submit(service, card)
    check(len(rpc.calls) == 1 and completed["card"]["status"] == "COMPLETED")
    check(completed["card"]["display"]["readOnly"] is True)
    check(completed["card"]["result"] == {"recordId": "synthetic-result"})
    check(completed["continuation"]["kind"] == "WRITE_APPROVAL")
    check(assets.prepare_approval("ability", ARGUMENTS, "tool-write") == completed["card"])
    check(assets._waiting_action is None)
    check(submit(service, card) == completed and len(rpc.calls) == 1)
    rejected(lambda: submit(service, card, request="request-2"))
    check(len(rpc.calls) == 1)
    observations = [row["payload"] for row in memory.observations.values()]
    check(any(item.get("businessSuccess") is True and item.get("result") == {"recordId": "synthetic-result"}
              for item in observations))

    assets, rpc, store, memory, service, factory = fixture()
    card = assets.execute_ability("ability", ARGUMENTS, tool_call_id="concurrent")["approvalCard"]
    def concurrent_submit(_):
        try:
            return submit(service, card)["card"]["status"]
        except ActionRejected as error:
            return error.code
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(concurrent_submit, range(8)))
    check(len(rpc.calls) == 1 and "COMPLETED" in outcomes)
    check(set(outcomes) <= {"COMPLETED", "ACTION_REQUEST_BUSY", "CARD_BUSY"})

    assets, rpc, store, memory, service, factory = fixture()
    card = assets.execute_ability("ability", ARGUMENTS, tool_call_id="binding-check")["approvalCard"]
    metadata = store.get_binding(OWNER, "731", card["cardId"])["metadata"]
    store.claim(OWNER, "731", card["cardId"], "claim", "submit", {"confirmation": ["approve"]})
    readonly = completed_interaction(card["display"], {"status": "SUBMITTED", "values": {"confirmation": ["approve"]}})
    changed = copy.deepcopy(metadata)
    changed["approval"]["arguments"]["title"] = "tampered"
    rejected(lambda: store.finish(OWNER, "731", card["cardId"], "claim", {}, True, True,
                                 prepared=readonly, binding_metadata=changed), "CARD_BINDING_MISMATCH")
    check(store.read(OWNER, "731", card["cardId"])["status"] == "EXECUTING")

    # Original handling task and tool call survive the approval round trip.
    assets, rpc, store, memory, service, factory = fixture()
    context = {"taskId": "task", "activityId": "activity", "runId": "source-run",
               "attentionId": "attention", "conversationId": "731", "objective": "synthetic",
               "status": "OPEN"}
    assets._processing_context, assets._processing_turn_id = context, "41"
    class Provider:
        def execute_operation(self, **kwargs):
            check(kwargs["turn_id"] == "41" and kwargs["task_id"] == "task")
            check(kwargs["tool_call_id"] == "handling-tool")
            claimed = store.read(OWNER, "731", kwargs["confirmation_card_id"])
            check(claimed["status"] == "EXECUTING")
            result = kwargs["invoke"]("processing:synthetic")
            return {"status": "RETURNED", "operationId": "operation", "requestId": "processing:synthetic",
                    "replayed": False, "result": result, "errorCode": None}
    assets._processing_provider = Provider()
    card = assets.execute_ability("ability", ARGUMENTS, tool_call_id="handling-tool")["approvalCard"]
    check(not rpc.calls)
    handled = submit(service, card)
    check(handled["card"]["result"]["status"] == "RETURNED" and len(rpc.calls) == 1)
    check(factory[0][1]["processing_context"] == context and factory[0][1]["processing_turn_id"] == "41")
    check(submit(service, card) == handled and len(rpc.calls) == 1)

    assets, rpc, store, memory, service, factory = fixture(fail=True)
    card = assets.execute_ability("ability", ARGUMENTS, tool_call_id="unknown")["approvalCard"]
    rejected(lambda: submit(service, card), "ACTION_OUTCOME_UNKNOWN")
    rejected(lambda: submit(service, card), "ACTION_OUTCOME_UNKNOWN")
    check(len(rpc.calls) == 1 and store.read(OWNER, "731", card["cardId"])["status"] == "UNKNOWN")
    rejected(lambda: assets.prepare_approval("ability", ARGUMENTS, "unknown"), "ACTION_OUTCOME_UNKNOWN")

    # Same-owner durable claim and frozen arguments are mandatory for handling
    # tasks. A second waiting card blocks this exception to WAITING_INPUT.
    metadata = {"definitionSource": "TEMPORARY", "processingTaskId": "task",
        "approvalProcessingContext": {"taskId": "task", "conversationId": "731"},
        "approvalProcessingTurnId": "41", "toolCallId": "tool-write", "approval": binding}
    payload = {"actionName": "submit", "inputs": {"confirmation": ["approve"]}}
    encoded = json.dumps(ARGUMENTS, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    class Connection:
        def __init__(self, row, other=False):
            self.row, self.other, self.calls = row, other, 0

        def execute(self, sql, params):
            self.calls += 1
            if self.calls == 1:
                check("r.state='CLAIMED'" in sql and "c.status='EXECUTING'" in sql)
                check(params == (OWNER.user_id, "PRT", 731, "task", "card"))
                return SimpleNamespace(fetchone=lambda: self.row)
            return SimpleNamespace(fetchone=lambda: {"found": 1} if self.other else None)

    def eligible(meta, *, other=False, missing=False):
        connection = Connection(None if missing else {"binding_metadata": meta, "payload": payload}, other)
        return ProcessingTasksRepository._confirmed_write(connection, (OWNER.user_id, "PRT", 731),
            "task", "card", "41", "tool-write", "demo.write", encoded)

    check(eligible(metadata))
    check(not eligible(metadata, other=True))
    check(not eligible(metadata, missing=True))
    for path, replacement in (("processingTaskId", "other-task"),
                              ("approvalProcessingTurnId", "other-turn"), ("toolCallId", "other-tool")):
        modified = copy.deepcopy(metadata)
        modified[path] = replacement
        check(not eligible(modified))
    for field, replacement in (("user_id", 9123402), ("environment", "ONLINE"),
                               ("run_id", "732"), ("action_code", "other.write"),
                               ("arguments_digest", "tampered")):
        modified = copy.deepcopy(metadata)
        modified["approval"]["receipt"][field] = replacement
        check(not eligible(modified))
    a2ui_probe()
    print(json.dumps({"probe": "chat-write-approval", "result": "PASS", "checks": checks}))


if __name__ == "__main__":
    main()
