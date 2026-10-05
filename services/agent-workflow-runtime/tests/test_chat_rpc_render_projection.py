"""Real RPC Chat render projection through the public Chat Tool."""

import hashlib
import json
import unittest
from threading import Lock
from types import MappingProxyType, SimpleNamespace
from typing import cast

from a2flow_asset_store.java_runtime import PROFILE
from agent_workflow_runtime.chat.rpc_assets import RpcChatAssets
from agent_workflow_runtime.chat.tools import build_chat_tools
from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.rpc_client import (
    CatalogDescriptor,
    ReleaseIdentity,
    RuntimeResult,
    RuntimeSession,
    freeze,
)
from agent_workflow_runtime.rpc_client import (
    JsonObject as RpcJsonObject,
)
from langchain.tools import ToolRuntime
from skillweave_contracts import TrustedContext
from skillweave_contracts.models import (
    ConversationInvocationScope,
    TrustedInvocationContext,
)

OWNER = TrustedContext(1009, "PRT")


class RpcChatRenderProjectionTests(unittest.TestCase):
    def test_query_contract_uses_published_description_and_runtime_schema(
        self,
    ) -> None:
        params_schema = {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
            "additionalProperties": False,
        }
        payload = json.dumps({
            "appCode": "draft-editor",
            "description": "Edit and review a saved draft.",
            "paramsSchema": params_schema,
            "catalog": {"catalogId": "catalog", "digest": "sha256:catalog"},
            "componentTypes": [],
        }, separators=(",", ":"), sort_keys=True)
        record = {
            "definition": {
                "runtimeProfile": PROFILE,
                "assetKey": "draft-editor",
                "sourceId": "source-1",
                "sourceDigest": "sha256:" + "0" * 64,
                "payloadDigest": hashlib.sha256(payload.encode()).hexdigest(),
                "payloadJson": payload,
            },
        }
        assets = object.__new__(RpcChatAssets)
        runtime = SimpleNamespace(params_schema=params_schema)
        assets.application_description = lambda application_key: (record, runtime)

        self.assertEqual(
            {
                "appCode": "draft-editor",
                "description": "Edit and review a saved draft.",
                "usage": (
                    "Call render_application with this appCode and params that "
                    "satisfy paramsSchema."
                ),
                "paramsSchema": params_schema,
            },
            assets._application_contract("draft-editor"),
        )

        runtime.params_schema = {"type": "object"}
        with self.assertRaisesRegex(
            ActionRejected, "APPLICATION_CONTRACT_INVALID",
        ):
            assets._application_contract("draft-editor")

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
        snapshot = (
            {"createSurface": {"surfaceId": "main", "catalogId": "catalog"}},
            {"updateComponents": {"surfaceId": "main", "components": [
                {"id": "root", "component": "Column", "children": [
                    "heading", "people", "field", "password", "computed",
                    "secret", "submit",
                ]},
                {"id": "heading", "component": "Text", "text": {"path": "/title"}},
                {"id": "people", "component": "ChoicePicker", "label": "人员列表",
                 "options": [
                     {"label": f"Person {index}", "value": f"p{index}"}
                     for index in range(1, 6)
                 ], "value": {"path": "/selected"}},
                {"id": "field", "component": "TextField", "label": "稿件标题",
                 "value": {"path": "/fieldValue"}},
                {"id": "password", "component": "TextField", "label": "密码",
                 "variant": "obscured", "value": {"path": "/password"}},
                {"id": "computed", "component": "Text",
                 "text": {"call": "formatString", "args": {}}},
                {"id": "secret", "component": "Text",
                 "text": {"path": "/credential"}},
                {"id": "submit", "component": "Button", "child": "submitText",
                 "action": {"event": {"name": "must-not-leak"}}},
                {"id": "submitText", "component": "Text", "text": "保存"},
                {"id": "orphan", "component": "Text", "text": "must-not-appear"},
            ]}},
            {"updateDataModel": {
                "surfaceId": "main",
                "path": "/",
                "value": {
                    "title": "canonical title",
                    "fieldValue": "draft title",
                    "password": "must-not-leak",
                    "selected": ["p1"],
                    "credential": "must-not-leak",
                    "nested": {
                        "cookie": "must-not-leak",
                        "safe": "kept",
                    },
                },
            }},
        )
        frozen_snapshot = cast(tuple[RpcJsonObject, ...], freeze(snapshot))
        self.assertIsInstance(frozen_snapshot[0], MappingProxyType)
        result = RuntimeResult(
            release=release,
            params={"modelInput": "not-rendered-state"},
            messages=frozen_snapshot,
            snapshot=frozen_snapshot,
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
        )[4]
        message = render_tool.invoke({
            "name": "render_application",
            "args": {
                "appCode": "draft-editor",
                "params": {"modelInput": "not-rendered-state"},
                "runtime": runtime,
            },
            "id": "render-call",
            "type": "tool_call",
        })

        content = json.loads(message.content)
        rendered = content["renderedApplication"]
        self.assertEqual("card-rpc-render", rendered["cardId"])
        self.assertEqual("draft-editor", rendered["appCode"])
        self.assertEqual(
            [{
                "surfaceId": "main",
                "data": {
                    "title": "canonical title",
                    "fieldValue": "draft title",
                    "selected": ["p1"],
                    "nested": {"safe": "kept"},
                },
            }],
            rendered["arguments"]["surfaces"],
        )
        self.assertEqual(
            [{
                "surfaceId": "main",
                "content": [
                    {"kind": "text", "text": "canonical title"},
                    {"kind": "choice", "label": "人员列表", "options": [
                        {"label": f"Person {index}", "value": f"p{index}"}
                        for index in range(1, 6)
                    ], "selectedValues": ["p1"]},
                    {"kind": "field", "label": "稿件标题", "value": "draft title"},
                    {"kind": "field", "label": "密码"},
                    {"kind": "button", "text": "保存"},
                ],
            }],
            rendered["preparedContent"]["surfaces"],
        )
        self.assertIn("does not assert", content["visibility"])
        self.assertNotIn("credential", message.content)
        self.assertNotIn("cookie", message.content)
        self.assertNotIn("updateDataModel", message.content)
        self.assertNotIn("protocol", message.content.lower())
        self.assertNotIn("not-rendered-state", message.content)
        self.assertNotIn("must-not-appear", message.content)
        self.assertNotIn("formatString", message.content)
        self.assertNotIn("event", message.content)
        self.assertEqual(
            rendered["arguments"],
            saved_metadata[0][1]["observation"]["arguments"],
        )


if __name__ == "__main__":
    unittest.main()
