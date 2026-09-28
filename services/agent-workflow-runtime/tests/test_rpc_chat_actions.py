"""Action observations preserve business facts when presentation fails."""

import unittest
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

from agent_workflow_runtime.chat.cards import ActionObservation
from agent_workflow_runtime.chat.rpc_actions import RpcChatActionService
from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.rpc_client import (
    ActionExecutionObservation,
    ReleaseIdentity,
    RuntimeSession,
)
from skillweave_contracts import TrustedContext


class RpcChatActionObservationTests(unittest.TestCase):
    def test_presentation_failure_keeps_actual_arguments_result_and_business_status(self) -> None:
        owner = TrustedContext(1009, "PRT")
        release = ReleaseIdentity("app", "source", "sha256:source", "build-1", "PRT")
        session = RuntimeSession("token", "build-1", "v0.9.1", "catalog", "1", "digest")
        card = {
            "cardId": "card-1",
            "revision": 0,
            "display": {
                "protocolProfile": "a2flow.java-rpc.v1",
                "applicationKey": "app",
                "applicationVersion": "version-1",
                "snapshotMessages": [{"version": "v0.9.1"}],
                "actions": [{
                    "surfaceId": "main",
                    "componentId": "save",
                    "actionName": "save",
                }],
            },
        }
        metadata = {
            "skillKey": "skill",
            "recordedVersions": [["SKILL:skill", "version-1"]],
            "rpc": {
                "release": asdict(release),
                "session": asdict(session),
                "params": {"projectId": "project-1"},
            },
        }
        store = Mock()
        store.get_binding.return_value = {"card": card, "metadata": metadata}
        store.replay.return_value = None
        store.claim.return_value = {"dispatch": True, "card": card, "metadata": metadata}
        store.fail.return_value = {**card, "status": "UNKNOWN", "revision": 2}

        assets = Mock()
        assets.application_description.return_value = ({}, SimpleNamespace(release=release))
        assets.action_descriptions.return_value = {"content.manuscript.save": "保存稿件"}
        assets.rpc.act.return_value = SimpleNamespace(
            action_observation=ActionExecutionObservation(
                binding_id="save-binding",
                action_code="content.manuscript.save",
                arguments={"title": "真实标题", "kind": "MANUSCRIPT"},
                result={"artifactId": "artifact-1", "revision": 3},
                capability_success=True,
                business_success=True,
                capability_error_code=None,
                presentation_error_code="A2UI_ADAPTER_SOURCE_MISSING",
            )
        )
        service = RpcChatActionService(store, lambda *_: assets)

        actual = service.execute(
            owner,
            "conversation-1",
            "card-1",
            request_id="request-1",
            action_name="save",
            inputs={"surfaceId": "main", "sourceComponentId": "save", "context": {}},
            expected_revision=0,
        )

        self.assertEqual("UNKNOWN", actual["status"])
        store.finish.assert_not_called()
        observation = store.fail.call_args.kwargs["observation"]
        self.assertIsInstance(observation, ActionObservation)
        self.assertEqual({"title": "真实标题", "kind": "MANUSCRIPT"}, observation.arguments)
        self.assertEqual({"artifactId": "artifact-1", "revision": 3}, observation.result)
        self.assertTrue(observation.capability_success)
        self.assertTrue(observation.business_success)
        self.assertEqual("FAILED", observation.presentation_status)
        self.assertEqual("A2UI_ADAPTER_SOURCE_MISSING", observation.presentation_error_code)
        self.assertEqual("保存稿件", observation.description)
        assets.action_description.assert_not_called()

    def test_post_dispatch_failure_does_not_discard_known_observation(self) -> None:
        owner = TrustedContext(1009, "PRT")
        release = ReleaseIdentity("app", "source", "sha256:source", "build-1", "PRT")
        session = RuntimeSession("token", "build-1", "v0.9.1", "catalog", "1", "digest")
        card = {
            "cardId": "card-1",
            "revision": 0,
            "display": {
                "protocolProfile": "a2flow.java-rpc.v1",
                "applicationKey": "app",
                "applicationVersion": "version-1",
                "snapshotMessages": [{"version": "v0.9.1"}],
                "actions": [{
                    "surfaceId": "main",
                    "componentId": "save",
                    "actionName": "save",
                }],
            },
        }
        metadata = {
            "skillKey": "skill",
            "recordedVersions": [["SKILL:skill", "version-1"]],
            "rpc": {
                "release": asdict(release),
                "session": asdict(session),
                "params": {"projectId": "project-1"},
            },
        }
        store = Mock()
        store.get_binding.return_value = {"card": card, "metadata": metadata}
        store.replay.return_value = None
        store.claim.return_value = {"dispatch": True, "card": card, "metadata": metadata}
        store.fail.return_value = {**card, "status": "UNKNOWN", "revision": 2}
        assets = Mock()
        assets.application_description.return_value = ({}, SimpleNamespace(release=release))
        assets.action_descriptions.return_value = {"content.manuscript.save": "保存稿件"}
        # Deliberately lacks RuntimeResult.release: runtime_metadata will fail only
        # after the actual execution observation has been constructed.
        assets.rpc.act.return_value = SimpleNamespace(
            action_observation=ActionExecutionObservation(
                binding_id="save-binding",
                action_code="content.manuscript.save",
                arguments={"title": "真实标题"},
                result={"artifactId": "artifact-1"},
                capability_success=True,
                business_success=True,
                capability_error_code=None,
                presentation_error_code=None,
            )
        )
        service = RpcChatActionService(store, lambda *_: assets)

        with self.assertRaisesRegex(ActionRejected, "ACTION_OUTCOME_UNKNOWN"):
            service.execute(
                owner,
                "conversation-1",
                "card-1",
                request_id="request-1",
                action_name="save",
                inputs={"surfaceId": "main", "sourceComponentId": "save", "context": {}},
                expected_revision=0,
            )

        observation = store.fail.call_args.kwargs["observation"]
        self.assertEqual({"artifactId": "artifact-1"}, observation.result)
        self.assertTrue(observation.capability_success)
        self.assertTrue(observation.business_success)


if __name__ == "__main__":
    unittest.main()
