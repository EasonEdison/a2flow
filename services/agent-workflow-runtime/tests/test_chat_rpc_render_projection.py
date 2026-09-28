"""Real RPC Chat render projection through the public Chat Tool."""

import json
import unittest
from threading import Lock
from types import SimpleNamespace

from langchain.tools import ToolRuntime
from skillweave_contracts import TrustedContext
from skillweave_contracts.models import (
    ConversationInvocationScope,
    TrustedInvocationContext,
)

from agent_workflow_runtime.chat.rpc_assets import RpcChatAssets
from agent_workflow_runtime.chat.tools import build_chat_tools
from agent_workflow_runtime.rpc_client import (
    CatalogDescriptor,
    ReleaseIdentity,
    RuntimeResult,
    RuntimeSession,
)


OWNER = TrustedContext(1009, "PRT")


class RpcChatRenderProjectionTests(unittest.TestCase):
    def test_tool_uses_canonical_business_state_and_omits_protocol_and_secrets(
        self,
    ) -> None:
        release = ReleaseIdentity(
            "draft-editor",
            "source-1",
            "sha256:source",
            "build-1",
            "PRT",
        )
        catalog = CatalogDescriptor("v0.9.1", "catalog", "1", "digest")
        session = RuntimeSession(
            "private-session",
            "build-1",
            "v0.9.1",
            "catalog",
            "1",
            "digest",
        )
        snapshot = ({
            "updateDataModel": {
                "surfaceId": "main",
                "path": "/",
                "value": {
                    "title": "canonical title",
                    "credential": "must-not-leak",
                    "nested": {
                        "cookie": "must-not-leak",
                        "safe": "kept",
                    },
                },
            },
        },)
        result = RuntimeResult(
            release=release,
            params={"modelInput": "not-rendered-state"},
            messages=snapshot,
            snapshot=snapshot,
            executions=(),
            actions=(),
            complete_interaction=False,
            selected_branch_id="",
            catalog=catalog,
            session=session,
            interaction_mode="DISPLAY_ONLY",
            business_success=True,
        )
        saved_metadata = []

        assets = object.__new__(RpcChatAssets)
        assets._owner = OWNER
        assets._conversation_id = "conversation-rpc-render"
        assets._control_request_id = "control-rpc-render"
        assets._admission = SimpleNamespace(
            skill_key="draft-writing",
            recorded_versions=(("SKILL:draft-writing", "version-1"),),
        )
        assets._waiting_action = None
        assets._render_lock = Lock()
        assets._render_observations = {}
        assets._card_sink = lambda prepared, metadata: (
            saved_metadata.append((prepared, metadata))
            or {"cardId": "card-rpc-render"}
        )
        assets.check_versions = lambda: ()
        assets.application_description = lambda application_key: (
            {"versionId": "application-version-1"},
            SimpleNamespace(release=release),
        )
        assets.rpc = SimpleNamespace(activate=lambda *args: result)

        invocation = TrustedInvocationContext(
            trusted_context=OWNER,
            invocation_scope=ConversationInvocationScope(
                conversation_id="conversation-rpc-render",
            ),
            control_request_id="control-rpc-render",
        )
        runtime = ToolRuntime(
            state=None,
            context=invocation,
            config={"configurable": {"thread_id": "conversation-rpc-render"}},
            stream_writer=None,
            tool_call_id="render-call",
            store=None,
        )
        render_tool = build_chat_tools(
            reader=object(),
            trusted_context=OWNER,
            conversation_id="conversation-rpc-render",
            control_request_id="control-rpc-render",
            chat_assets=assets,
        )[3]
        message = render_tool.invoke({
            "name": "render_application",
            "args": {
                "applicationKey": "draft-editor",
                "data": {"modelInput": "not-rendered-state"},
                "runtime": runtime,
            },
            "id": "render-call",
            "type": "tool_call",
        })

        content = json.loads(message.content)
        rendered = content["renderedApplication"]
        self.assertEqual("card-rpc-render", rendered["cardId"])
        self.assertEqual("draft-editor", rendered["applicationKey"])
        self.assertEqual(
            [{
                "surfaceId": "main",
                "data": {
                    "title": "canonical title",
                    "nested": {"safe": "kept"},
                },
            }],
            rendered["arguments"]["surfaces"],
        )
        self.assertIn("does not assert", content["visibility"])
        self.assertNotIn("credential", message.content)
        self.assertNotIn("cookie", message.content)
        self.assertNotIn("updateDataModel", message.content)
        self.assertNotIn("protocol", message.content.lower())
        self.assertNotIn("not-rendered-state", message.content)
        self.assertEqual(
            rendered["arguments"],
            saved_metadata[0][1]["observation"]["arguments"],
        )


if __name__ == "__main__":
    unittest.main()
