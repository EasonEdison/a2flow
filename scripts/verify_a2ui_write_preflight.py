#!/usr/bin/env python3
"""Synthetic A2UI PrepareAct -> explicit receipt -> Act; no network, DB, or model."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in ("packages/rpc-contracts/src", "services/capability-execution/src", "services/a2ui-execution/src"):
    sys.path.insert(0, str(ROOT / directory))
from a2flow.a2ui.v1 import a2ui_pb2 as ui
from a2flow.capability.v1 import capability_pb2 as cap
from a2flow_capability.approval import ApprovalGuard
from a2flow_capability.compiler import CompiledCapability
from a2flow_capability.executor import CapabilityExecutor
from a2flow_capability.invoker import PublishedCapabilityInvoker
from a2flow_capability.models import (ArgumentDefinition, Environment, JsonKind, JsonObject, PublishedPlan,
    RequestMapping, TrustedContext, ValueSchema)
from a2flow_a2ui.models import ApplicationBuild, ApplicationRelease, PublishedApplication
from a2flow_a2ui.runtime import A2uiRuntimeService
from a2flow_a2ui.rpc import A2uiRpcService

CHECKS = 0

def check(condition, message):
    global CHECKS
    if not condition:
        raise AssertionError(message)
    CHECKS += 1

def build_json() -> JsonObject:
    return {
        "appBuildId": "build-1",
        "appCode": "demo.app",
        "description": "Demo application",
        "sourceDigest": "sha256:build",
        "protocolVersion": "v0.9.1",
        "protocolStatus": "ACTIVE",
        "protocolSourceCommit": "abc",
        "protocolSchemaDigests": {},
        "publicationEnvironment": "PRT",
        "catalog": {
            "catalogId": "catalog",
            "revision": "1",
            "digest": "sha256:catalog",
            "catalogSourceType": "LOCAL",
            "componentOrigins": {"Button": "STANDARD"},
        },
        "showTemplateCode": "show",
        "showTemplateDigest": "sha256:show",
        "paramsSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
        },
        "surfaceDeclarations": [
            {"surfaceId": "main", "rootComponentId": "root", "footerComponentIds": []}
        ],
        "initialMessages": [
            {
                "version": "v0.9.1",
                "createSurface": {"surfaceId": "main", "root": "root"},
            },
            {
                "version": "v0.9.1",
                "updateComponents": {
                    "surfaceId": "main",
                    "components": [
                        {"id": "root", "type": "Column", "children": ["submit"]},
                        {"id": "submit", "type": "Button", "label": "placeholder"},
                    ],
                },
            },
        ],
        "inputBindings": [
            {
                "targetMessageIndex": 1,
                "targetPath": "/updateComponents/components/1/label",
                "source": "APP_PARAMS",
                "sourcePath": "/title",
                "required": True,
                "constantValue": None,
            }
        ],
        "componentTypes": ["Column", "Button"],
        "capabilitySchemaAudits": [],
        "actionDeclarations": [
            {
                "surfaceId": "main",
                "sourceComponentId": "submit",
                "actionCode": "demo.submit",
                "contextTemplateDigest": "sha256:context",
            }
        ],
        "loadBindings": [],
        "actionBindings": [
            {
                "bindingId": "submit-binding",
                "surfaceId": "main",
                "sourceComponentId": "submit",
                "actionCode": "demo.submit",
                "declarationDigest": "sha256:context",
                "allowedSourceComponentIds": ["submit"],
                "contextSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
                "capability": {"actionCode": "demo.submit"},
                "requestMappings": [
                    {
                        "source": "ACTION_CONTEXT",
                        "sourcePath": "/name",
                        "targetPath": "/name",
                        "constantValue": None,
                    }
                ],
                "successOutcome": "ADAPTER_PIPELINE",
                "failureOutcome": "NO_UI_MESSAGES",
                "resultAdapters": [
                    {
                        "adapterId": "success",
                        "order": 1,
                        "type": "MESSAGE_TEMPLATE",
                        "templateCode": "result",
                        "templateRevision": "1",
                        "templateDigest": "sha256:result",
                        "messageTemplate": {
                            "version": "v0.9.1",
                            "updateDataModel": {
                                "surfaceId": "main",
                                "path": "/",
                                "value": {},
                            },
                        },
                        "bindings": [
                            {
                                "targetPath": "/updateDataModel/value/greeting",
                                "source": "CAPABILITY_DATA",
                                "sourcePath": "/greeting",
                                "required": True,
                                "constantValue": None,
                            }
                        ],
                        "source": None,
                        "sourcePath": None,
                        "cardinality": None,
                        "required": False,
                        "emittedActionDeclarations": [],
                    }
                ],
                "failureResultAdapters": [],
                "businessSuccessPredicate": {
                    "version": "JSON_POINTER_V1",
                    "allOf": [
                        {
                            "source": "CAPABILITY_DATA",
                            "sourcePath": "/decisionType",
                            "operator": "EQUALS",
                            "expectedValue": "READING",
                        }
                    ],
                },
                "completeWorkflowInteractionOnSuccess": True,
                "successBranches": [],
            }
        ],
        "interactionMode": "INTERACTIVE",
    }


class Transport:
    def __init__(self):
        self.calls = []
    def execute(self, plan, business, context):
        self.calls.append(copy.deepcopy(business))
        return {"decisionType": "READING", "greeting": "hello " + business["name"]}

class Store:
    def __init__(self):
        self.consumed = set()
    def consume(self, receipt):
        if receipt.receipt_id in self.consumed:
            return False
        self.consumed.add(receipt.receipt_id)
        return True

class Invoker(PublishedCapabilityInvoker):
    def __init__(self, level="WRITE"):
        self.transport, self.store = Transport(), Store()
        self._executor = CapabilityExecutor(self.transport, approval_guard=ApprovalGuard(self.store))
        self.plan = PublishedPlan(source_id="probe-source", source_digest="probe-digest", resolved_environment=Environment.PRT,
            action_code="demo.submit", capability_version=1, client_type="PC", target_key="probe",
            service_name="probe.Business", method_name="Invoke", descriptor_set_base64="ZGVzY3JpcHRvcg==",
            context_field="context", timeout_ms=1000, max_response_bytes=100000, technical_output_schema={"type":"object"},
            arguments=(ArgumentDefinition("name", ValueSchema(JsonKind.STRING), True),),
            request_mappings=(RequestMapping("name", "name"),), side_effect_level=level, approval_policy="REQUEST_APPROVAL")
    def _resolve_action_code(self, action_code, context):
        check(action_code == "demo.submit", "bound action")
        return "probe-asset", CompiledCapability(self.plan, "synthetic", {"type":"object"}, [])

class Releases:
    def __init__(self):
        self.published = PublishedApplication(
            ApplicationRelease("demo.app", "app-build", "sha256:app", "build-1", Environment.PRT),
            ApplicationBuild.model_validate(build_json()))
    def current(self, app, owner):
        check(app == "demo.app" and owner.environment is Environment.PRT, "bound app/environment")
        return self.published

class Context:
    def abort(self, status, detail):
        raise RuntimeError(detail)

def request(runtime):
    owner = TrustedContext(77, Environment.PRT, "action-probe", "PC")
    activated = runtime.activate("demo.app", {"title": "synthetic"}, owner)
    message = {"version": "v0.9.1", "action": {"name": "demo.submit", "surfaceId": "main",
        "sourceComponentId": "submit", "timestamp": "2026-01-01T00:00:00Z", "context": {"name": "synthetic"}}}
    return ui.ActRequest(context=cap.ExecutionContext(user_id=77, environment=cap.PRT, request_id="action-probe", client="PC"),
        card=ui.TrustedCard(user_id=77, app_code="demo.app", params_json=b'{"title":"synthetic"}',
                           snapshot_json=json.dumps(activated.snapshot).encode()),
        correlation_id="probe-card", idempotency_key="action-probe", action_message_json=json.dumps(message).encode())

def main():
    invoker = Invoker()
    runtime = A2uiRuntimeService(Releases(), invoker)
    service = A2uiRpcService(runtime)
    original = request(runtime)
    prepared = service.PrepareAct(original, Context())
    check(not invoker.transport.calls and not invoker.store.consumed, "preflight cannot consume or execute")
    check(prepared.capability.side_effect_level == "WRITE" and prepared.capability.approval_policy == "REQUEST_APPROVAL", "strict policy")
    check(prepared.arguments_json == b'{"name":"synthetic"}', "exact canonical mapping")
    check(prepared.binding_id == "submit-binding", "binding identity")
    rejected = service.Act(original, Context())
    check(rejected.action_observation.capability_error_code == "APPROVAL_REQUIRED" and not invoker.transport.calls,
          "unapproved Act does not execute")
    receipt = cap.ApprovalReceipt(receipt_id="probe-confirm", confirmation_id="probe-confirm", user_id=77,
        environment=cap.PRT, run_id="probe-chat", tool_call_id="probe-action", action_code="demo.submit",
        source_id=prepared.capability.source_id, source_digest=prepared.capability.source_digest,
        arguments_digest=hashlib.sha256(prepared.arguments_json).hexdigest(), side_effect_level="WRITE", approval_policy="REQUEST_APPROVAL")
    changed = ui.ActRequest(); changed.CopyFrom(original); changed.approval_receipt.CopyFrom(receipt)
    value = json.loads(changed.action_message_json); value["action"]["context"]["name"] = "changed"
    changed.action_message_json = json.dumps(value).encode()
    rejected = service.Act(changed, Context())
    check(rejected.action_observation.capability_error_code == "APPROVAL_INVALID" and not invoker.transport.calls,
          "changed mapping cannot use frozen confirmation")
    changed.CopyFrom(original); changed.approval_receipt.CopyFrom(receipt); changed.approval_receipt.source_digest = "changed-source"
    rejected = service.Act(changed, Context())
    check(rejected.action_observation.capability_error_code == "APPROVAL_INVALID" and not invoker.transport.calls,
          "changed release cannot execute")
    other_owner = ui.ActRequest(); other_owner.CopyFrom(original); other_owner.card.user_id = 88
    try:
        service.PrepareAct(other_owner, Context())
    except RuntimeError as error:
        check(str(error) == "A2UI_CARD_CONTEXT_MISMATCH", "foreign-owner preflight rejected")
    else:
        raise AssertionError("foreign owner accepted")
    check(not invoker.transport.calls, "foreign preflight does not execute")
    approved = ui.ActRequest(); approved.CopyFrom(original); approved.approval_receipt.CopyFrom(receipt)
    result = service.Act(approved, Context())
    check(result.business_success and result.complete_interaction and len(invoker.transport.calls) == 1,
          "confirmed Act executes and completes original interaction")
    check(json.loads(result.action_observation.result_json)["greeting"] == "hello synthetic", "real result preserved")
    repeated = service.Act(approved, Context())
    check(repeated.action_observation.capability_error_code == "APPROVAL_ALREADY_CONSUMED"
          and len(invoker.transport.calls) == 1, "receipt cannot re-dispatch")
    reads = Invoker("READ"); read_runtime = A2uiRuntimeService(Releases(), reads); read_service = A2uiRpcService(read_runtime)
    read_request = request(read_runtime); read_preflight = read_service.PrepareAct(read_request, Context())
    check(read_preflight.capability.side_effect_level == "READ" and not reads.transport.calls, "read preflight is read-only")
    check(read_service.Act(read_request, Context()).business_success and len(reads.transport.calls) == 1,
          "READ needs no confirmation despite old REQUEST_APPROVAL")
    load_releases = Releases()
    raw = build_json()
    raw["loadBindings"] = [{"bindingId": "load-probe", "capability": {"actionCode": "demo.submit"},
        "requestMappings": [{"source": "CONSTANT", "targetPath": "/name", "constantValue": "synthetic"}],
        "successOutcome": "NO_UI_MESSAGES", "failureOutcome": "NO_UI_MESSAGES",
        "resultAdapters": [], "failureResultAdapters": []}]
    load_releases.published = PublishedApplication(load_releases.published.release, ApplicationBuild.model_validate(raw))
    write_loads = Invoker()
    loaded = A2uiRuntimeService(load_releases, write_loads).activate("demo.app", {"title":"synthetic"},
        TrustedContext(77, Environment.PRT, "load-probe", "PC"))
    check(not write_loads.transport.calls and loaded.executions[0].error_code == "APPROVAL_REQUIRED",
          "LOAD cannot authorize business writes")
    read_loads = Invoker("READ")
    loaded = A2uiRuntimeService(load_releases, read_loads).activate("demo.app", {"title":"synthetic"},
        TrustedContext(77, Environment.PRT, "load-probe", "PC"))
    check(len(read_loads.transport.calls) == 1 and loaded.executions[0].success, "READ LOAD unaffected")
    print(json.dumps({"probe":"a2ui-write-preflight","result":"PASS","checks":CHECKS}, separators=(",", ":")))

if __name__ == "__main__":
    main()
