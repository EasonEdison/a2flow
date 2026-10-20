#!/usr/bin/env python3
"""Offline real LangGraph interrupt/resume probe; synthetic RPC and test-only memory stores."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[1]
for relative in ("packages/contracts/src", "packages/asset-store/src", "services/b-side-api/src",
                 "services/agent-workflow-runtime/src", "services/skill-registry/src",
                 "services/capability-registry/src", "services/a2ui-composer/src",
                 "services/agent-workflow-runtime/tests"):
    sys.path.insert(0, str(ROOT / relative))

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, END, StateGraph
from langgraph.types import Command
from skillweave_contracts import TrustedContext
from agent_workflow_runtime.capability_approval import argument_bytes, receipt_for
from agent_workflow_runtime.chat.cards import ChatCardStore
from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.rpc_client import AbilityDescription, AbilityResult
from agent_workflow_runtime.temporary_interaction import TemporaryCandidate
from agent_workflow_runtime.workflow_rpc import WorkflowActions, WorkflowAssets, WorkflowCapabilityAssets
from agent_workflow_runtime.workflow_rpc_host import tools_for
from agent_workflow_runtime.workflow_capability import build_capability_graph, CapabilityState
from lifecycle_support import fixture
from support import Repository
from test_chat_cards import MemoryStorage

CHECKS = 0


def check(value, message):
    global CHECKS
    if not value:
        raise AssertionError(message)
    CHECKS += 1


def rejects(call, code=None):
    try:
        call()
    except ActionRejected as error:
        check(code is None or error.code == code, "expected rejection code")
    else:
        raise AssertionError("expected rejection")


class Rpc:
    def __init__(self, level):
        self.calls = []
        self.receipts = set()
        self.description = AbilityDescription("probe-asset", "probe.write", 1, "synthetic", {
            "type": "object", "properties": {}, "additionalProperties": False}, [],
            "PRT", "probe-source", "probe-digest", level, "REQUEST_APPROVAL")

    def resolve(self, *args):
        return self.description

    def execute(self, owner, asset, arguments, request_id, *, approval_receipt=None):
        if self.description.side_effect_level != "READ":
            check(approval_receipt is not None, "write has trusted receipt")
            receipt = approval_receipt
            check(receipt["user_id"] == owner.user_id and receipt["environment"] == owner.environment,
                  "receipt binds owner/environment")
            check(receipt["arguments_digest"] == hashlib.sha256(argument_bytes(arguments)).hexdigest(),
                  "receipt binds exact argument encoding")
            check(receipt["source_digest"] == self.description.source_digest, "receipt binds immutable source")
            if receipt["receipt_id"] in self.receipts:
                raise ActionRejected("APPROVAL_ALREADY_CONSUMED")
            self.receipts.add(receipt["receipt_id"])
        self.calls.append(copy.deepcopy(arguments))
        return AbilityResult(True, "probe.write", 1, "PRT", {"saved": True}, "", "", request_id,
                             "probe-source", "probe-digest")


class SkillAssets(WorkflowAssets):
    """Replace asset registry only; keep production card, approval and execute methods."""
    def admit_skill(self, key):
        if key != self.skill_key:
            raise ActionRejected("SKILL_NOT_BOUND_TO_NODE")
        self._admission = SimpleNamespace(skill_key=key)
        return {"content": {}, "artifact": {}}

    def _record(self, kind, key):
        self._require_admission()
        if kind != "ABILITY" or key != "probe.write":
            raise ActionRejected("ABILITY_NOT_ALLOWED")
        return {"definition": {"assetKey": "probe-asset"}, "versionId": "v1"}


class DirectAssets(WorkflowCapabilityAssets):
    def capability_record(self):
        return {"definition": {"assetKey": "probe-asset"}, "versionId": "v1"}


class State(TypedDict, total=False):
    done: bool


class ParameterGenerator:
    def generate(self, intent, data):
        return TemporaryCandidate(title="补充参数", mode="INTERACTIVE", components=[
            {"id": "root", "component": "Column", "children": ["choice", "submit"]},
            {"id": "choice", "component": "ChoicePicker", "label": "目标", "variant": "mutuallyExclusive",
             "options": [{"label": "合成目标", "value": "synthetic"}], "value": {"path": "/inputs/target"}},
            {"id": "submit", "component": "Button", "child": "label", "action": {"event": {
                "name": "submit", "context": {"target": {"path": "/inputs/target"}}}}},
            {"id": "label", "component": "Text", "text": "提交参数"},
        ], inputSchema={"type": "object", "properties": {"target": {"type": "array",
            "items": {"type": "string", "enum": ["synthetic"]}, "minItems": 1, "maxItems": 1}},
            "required": ["target"], "additionalProperties": False})


class Harness:
    def __init__(self, level="WRITE", direct=False, parameters=False):
        self.repository, self.lifecycle, self.run = fixture()
        self.rpc = Rpc(level)
        self.memory = MemoryStorage()
        self.store = ChatCardStore(None, environment="PRT", _storage=self.memory)
        self.interactions = Repository()
        self.direct = direct
        self.asset = self.make_assets()
        self.actions = WorkflowActions(self.interactions, self.lifecycle, self.store, None, self.rpc,
            self.run, {} if direct else {"node-test": "probe-skill"},
            {"node-test": "probe.write"} if direct else {})
        self.actions.assets = lambda node: self.asset
        self.outputs = []
        self.config = {"configurable": {"thread_id": self.run.thread_id}}
        if direct:
            binding = build_capability_graph(run=self.run,
                node={"nodeId": "node-test", "abilityKey": "probe.write"}, lifecycle=self.lifecycle,
                assets=self.asset, actions=self.actions,
                views=SimpleNamespace(output=lambda *args: self.outputs.append(args)), progress=None,
                create_model=lambda: (_ for _ in ()).throw(AssertionError("model must not run")))
            builder = StateGraph(CapabilityState)
            builder.add_node("direct", binding.graph)
            builder.add_edge(START, "direct"); builder.add_edge("direct", END)
            self.initial = {"messages": []}
        else:
            builder = StateGraph(State)
            if parameters:
                def collect(state):
                    self.actions.render_interaction(self.asset, {}, "补充目标", "parameter-call", ParameterGenerator())
                    return {}
                builder.add_node("parameters", collect)
                builder.add_edge(START, "parameters"); builder.add_edge("parameters", "write")
            else:
                builder.add_edge(START, "write")
            def execute(state):
                tool = next(item for item in tools_for(self.asset, self.actions) if item.name == "execute_ability")
                tool.func("probe.write", {"title": "synthetic"},
                          SimpleNamespace(context=self.run.context("node-test"), tool_call_id="write-call"))
                return {"done": True}
            builder.add_node("write", execute); builder.add_edge("write", END)
            self.initial = {}
        self.graph = builder.compile(checkpointer=MemorySaver())
        self.actions.continuation = lambda item, control: self.graph.invoke(
            Command(resume={"controlRequestId": control}), self.config,
            context=self.run.context("node-test"))

    def make_assets(self):
        kind = DirectAssets if self.direct else SkillAssets
        return kind(None, self.rpc, self.run, "node-test", "probe.write" if self.direct else "probe-skill", self.store)

    def start(self):
        return self.graph.invoke(self.initial, self.config, context=self.run.context("node-test"))

    def cards(self):
        return self.store.list(self.run.owner, self.asset.conversation_id)

    def waiting(self):
        cards = [card for card in self.cards() if card["status"] == "WAITING_ACTION"]
        check(len(cards) == 1, "one waiting card")
        return cards[0]

    def submit(self, card, request="submit-write", values=None):
        return self.actions.execute_card("node-test", card["cardId"], card["cardId"], request,
            "submit", {"confirmation": ["approve"]} if values is None else values)

    def resume(self, card, action_request="submit-write", control="resume-write"):
        self.actions.resume_card("node-test", card["cardId"], card["cardId"], control, action_request)


def main():
    read = Harness("READ")
    check(read.start().get("done") is True and len(read.rpc.calls) == 1, "READ executes")
    check(not read.cards(), "READ never creates approval card")

    skill = Harness()
    check(bool(skill.start().get("__interrupt__")), "real Skill native interrupt")
    card = skill.waiting()
    check(not skill.rpc.calls, "zero business before confirmation")
    rejects(lambda: skill.submit(card, values={"confirmation": []}))
    other = TrustedContext(skill.run.owner.user_id + 1, "PRT")
    rejects(lambda: skill.store.get_binding(other, skill.asset.conversation_id, card["cardId"]), "CARD_NOT_FOUND")
    saved = skill.store.get_binding(skill.run.owner, skill.asset.conversation_id, card["cardId"])["metadata"]["approval"]
    changed = copy.deepcopy(saved); changed["arguments"]["title"] = "changed"
    rejects(lambda: receipt_for(skill.run.owner, card["cardId"], changed), "WRITE_CONFIRMATION_BINDING_INVALID")
    check(not skill.rpc.calls, "rejected approvals do not execute")
    skill.submit(card)
    check(not skill.rpc.calls, "Flow submission only persists confirmation")
    skill.resume(card)
    check(len(skill.rpc.calls) == 1 and not skill.graph.get_state(skill.config).next, "Skill resumed and executed once")
    skill.resume(card)
    check(len(skill.rpc.calls) == 1, "duplicate control does not dispatch again")

    fresh = Harness()
    fresh.start(); fresh_card = fresh.waiting(); fresh.submit(fresh_card)
    fresh.asset = fresh.make_assets()
    fresh.resume(fresh_card)
    check(len(fresh.rpc.calls) == 1 and len(fresh.cards()) == 1, "new asset instance resumes original saved confirmation")

    parameters = Harness(parameters=True)
    check(bool(parameters.start().get("__interrupt__")), "parameter native interrupt")
    parameter = parameters.waiting()
    parameters.submit(parameter, "submit-parameters", {"target": ["synthetic"]})
    parameters.resume(parameter, "submit-parameters", "resume-parameters")
    approval = parameters.waiting()
    check(approval["cardId"] != parameter["cardId"] and not parameters.rpc.calls,
          "parameter completion is not approval")
    parameters.submit(approval); parameters.resume(approval)
    check(len(parameters.rpc.calls) == 1, "write executes after separate real confirmation")

    direct = Harness(direct=True)
    check(bool(direct.start().get("__interrupt__")), "direct capability native interrupt")
    direct_card = direct.waiting()
    check(not direct.rpc.calls, "direct write not dispatched before confirmation")
    direct.submit(direct_card); direct.resume(direct_card)
    check(len(direct.rpc.calls) == 1 and bool(direct.outputs), "direct capability resumed and result saved")
    direct.resume(direct_card)
    check(len(direct.rpc.calls) == 1, "direct duplicate resume cannot execute twice")
    check(not direct.graph.get_state(direct.config).next, "direct graph complete")
    print(json.dumps({"probe": "workflow-write-approval", "result": "PASS", "checks": CHECKS}, separators=(",", ":")))


if __name__ == "__main__":
    main()
