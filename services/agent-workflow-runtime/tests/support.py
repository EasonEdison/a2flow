"""Explicit in-memory test ports; not a production repository or persistence proof."""

from contextlib import contextmanager
from dataclasses import replace
import hashlib
from pathlib import Path
import json
from threading import RLock

from skillweave_contracts import TrustedContext, TrustedInvocationContext
from skillweave_contracts.models import JsonPointerEqualsPolicy
from agent_workflow_runtime import ActionConfig, ActionRejected, Interaction


ROOT = Path(__file__).resolve().parents[3]


def context():
    return TrustedInvocationContext.from_mapping({
        "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
        "trustedContext": {"userId": '1008', "environment": "PRT"},
        "invocationScope": {"kind": "WORKFLOW", "runId": "run-test", "nodeId": "node-test"},
        "controlRequestId": "original-render-request",
    })


class Repository:
    def __init__(self):
        self.items = {}
        self.lock = RLock()
        self.delivery_lock = RLock()

    @contextmanager
    def scope(self, owner, run_id):
        with self.lock:
            yield

    @contextmanager
    def continuation_scope(self, owner, run_id):
        with self.delivery_lock:
            yield

    def check_scope(self):
        pass

    def get(self, key, owner=None):
        item = self.items.get(key)
        return item if owner is None or item is None or item.context.trusted_context == owner else None

    def for_run(self, owner, run_id):
        return tuple(item for item in self.items.values()
                     if item.context.trusted_context == owner and item.key[0] == run_id)

    def save(self, interaction):
        self.items[interaction.key] = interaction

    def for_node(self, owner, run_id, node_id):
        return tuple(item for item in self.items.values()
                     if item.context.trusted_context == owner and item.key[:2] == (run_id, node_id))


class Configuration:
    def __init__(self):
        self.current = (("APPLICATION:sample.interactive.route-selection", "application-version-1"),
                        ("ABILITY:route", "ability-version-1"), ("SKILL:brief", "skill-version-1"))
        self.complete = True
        self.policy = JsonPointerEqualsPolicy("accepted", "/accepted", True)

    def versions(self, interaction):
        return self.current

    def action(self, interaction, name):
        if name not in ("confirm_route_choice", "save_choice"):
            raise ActionRejected("ACTION_NOT_ALLOWED")
        return ActionConfig(
            name, "route.select", self.current, self.policy,
            self.complete and name == "confirm_route_choice",
            lambda value: (
                isinstance(value, dict) and set(value) == {"selection"}
                and value["selection"] in ("left", "right")
            ),
            lambda value: isinstance(value, dict) and type(value.get("accepted")) is bool,
        )


class Executor:
    def __init__(self):
        self.result = {"accepted": True, "route": "left"}
        self.calls = []
        self.hook = None

    def __call__(self, config, inputs, owner):
        self.calls.append((config.operation_ref, inputs, owner))
        if self.hook:
            self.hook()
        return self.result


class Resolver:
    def __init__(self, config):
        self.config = config

    def __call__(self, key, trusted):
        name = ("interactive-selection-card.application.json" if key.endswith("route-selection")
                else "display-only-result-card.application.json")
        raw = (ROOT / "packages/a2ui-contract-fixtures/fixtures" / name).read_bytes()
        return {
            "application": json.loads(raw),
            "resolvedVersion": {"asset": {"assetId": key, "assetType": "APPLICATION"},
                                "versionId": "application-version-1"},
            "contentDigest": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "recordedVersions": self.config.current,
        }


def interaction(config, identity="interaction-test"):
    return Interaction(
        context(), identity, "sample.interactive.route-selection",
        "application-version-1", "graph-thread", config.current,
    )


def request(item, request_id="request-1", **changes):
    value = {
        "runId": item.key[0], "nodeId": item.key[1], "interactionId": item.key[2],
        "actionName": "confirm_route_choice", "controlRequestId": request_id,
        "inputs": {"selection": "left"},
    }
    value.update(changes)
    return value
