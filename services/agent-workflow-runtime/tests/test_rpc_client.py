"""Real loopback RPC transport with explicit test-only servicers, no business calls."""
import json
import unittest
from threading import Event
from concurrent.futures import ThreadPoolExecutor

import grpc
from a2flow.a2ui.v1 import a2ui_pb2 as ui, a2ui_pb2_grpc as ui_rpc
from a2flow.capability.v1 import capability_pb2 as cap, capability_pb2_grpc as cap_rpc
from agent_workflow_runtime.rpc_client import RpcClient, RpcFailure, TrustedCard, thaw
from skillweave_contracts import TrustedContext


class Fixture(ui_rpc.A2uiExecutionServicer, cap_rpc.CapabilityExecutionServicer):
    def __init__(self):
        self.calls = 0

    def release(self, context):
        assert context.HasField("user_id") and context.user_id == -(2**63)
        return ui.ApplicationRelease(app_code="app", source_id="source", digest="digest",
                                     app_build_id="build", environment=context.environment)

    def catalog(self):
        return ui.CatalogDescriptor(protocol_version="v0.9.1", catalog_id="catalog", catalog_revision="1", catalog_digest="cd")

    def Describe(self, request, context):
        return ui.DescribeResponse(release=self.release(request.context), params_schema_json=b'{"type":"object"}',
                                  interaction_mode="INTERACTIVE", catalog=self.catalog())

    def Activate(self, request, context):
        self.calls += 1
        assert json.loads(request.params_json)["exact"] == 2**63 - 1
        result = self.result(request.context, request.params_json)
        if request.context.request_id == "wrong-response":
            result.release.source_id = "unexpected-source"
        return result

    def result(self, context, params):
        return ui.RuntimeResponse(release=self.release(context), params_json=params,
            messages_json=b'[]', snapshot_json=b'[]', catalog=self.catalog(), interaction_mode="INTERACTIVE",
            business_success=True, session=ui.RuntimeSession(token="private", app_build_id="build",
            protocol_version="v0.9.1", catalog_id="catalog", catalog_revision="1", catalog_digest="cd"))

    def Act(self, request, context):
        assert request.card.HasField("user_id") and request.card.user_id == -(2**63)
        assert request.card.app_code == "app"
        assert request.idempotency_key == request.context.request_id
        return self.result(request.context, request.card.params_json)

    def Resolve(self, request, context):
        return cap.ResolveResponse(asset_key=request.asset_key, action_code="ability", capability_version=1,
            input_schema_json='{"type":"object"}', key_output_fields_json='[]',
            resolved_environment=cap.ONLINE if request.asset_key == "bad-env" else request.context.environment,
            source_id="ability-source", source_digest="ability-digest")

    def Execute(self, request, context):
        self.calls += 1
        if request.context.request_id == "timeout":
            Event().wait(0.05)
        return cap.ExecuteResponse(success=True, action_code="ability", capability_version=1,
            resolved_environment=request.context.environment, data_json=request.arguments_json,
            request_id=request.context.request_id, source_id="ability-source", source_digest="ability-digest")


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.server = grpc.server(ThreadPoolExecutor(max_workers=2))
        ui_rpc.add_A2uiExecutionServicer_to_server(self.fixture, self.server)
        cap_rpc.add_CapabilityExecutionServicer_to_server(self.fixture, self.server)
        self.port = self.server.add_insecure_port("127.0.0.1:0")
        self.server.start()
        self.client = RpcClient.from_environment({"A2FLOW_ENGINE_RPC_TARGET": f"127.0.0.1:{self.port}",
                                                  "A2FLOW_ENGINE_RPC_MODE": "LOOPBACK"})
        self.owner = TrustedContext(-(2**63), "PRT")

    def tearDown(self):
        self.client.close()
        self.server.stop(0).wait()

    def test_all_methods_and_exact_integer(self):
        description = self.client.describe(self.owner, "app", "describe")
        self.assertEqual(self.fixture.calls, 0)
        result = self.client.activate(self.owner, "app", {"exact": 2**63 - 1}, "activate")
        self.assertEqual(result.params["exact"], 2**63 - 1)
        with self.assertRaises(TypeError):
            result.params["exact"] = 0
        card = TrustedCard(self.owner.user_id, "app", result.params, result.snapshot)
        acted = self.client.act(self.owner, card, {"version": "v0.9.1", "action": {}}, "act", correlation_id="card")
        self.assertEqual(acted.session, result.session)
        ability = self.client.resolve(self.owner, "asset", "resolve")
        executed = self.client.execute(self.owner, "asset", {"exact": 2**63 - 1}, "execute")
        self.assertEqual(thaw(executed.data), {"exact": 2**63 - 1})
        self.assertEqual(executed.resolved_environment, "PRT")

    def test_execute_resolves_the_current_release_without_a_pinned_identity(self):
        result = self.client.execute(self.owner, "asset", {}, "execute")
        self.assertEqual(result.source_id, "ability-source")
        self.assertEqual(self.fixture.calls, 1)

    def test_activate_accepts_the_current_release_returned_by_the_service(self):
        result = self.client.activate(
            self.owner, "app", {"exact": 2**63 - 1}, "wrong-response",
        )
        self.assertEqual(result.release.source_id, "unexpected-source")
        self.assertEqual(self.fixture.calls, 1)

    def test_configuration_fails_closed(self):
        for config in ({}, {"A2FLOW_ENGINE_RPC_TARGET": "127.0.0.1:123", "A2FLOW_ENGINE_RPC_MODE": "MTLS"},
                       {"A2FLOW_ENGINE_RPC_TARGET": "example.com:123", "A2FLOW_ENGINE_RPC_MODE": "LOOPBACK"},
                       {"A2FLOW_ENGINE_RPC_TARGET": "127.0.0.1:123", "A2FLOW_ENGINE_RPC_MODE": "LOOPBACK",
                        "A2FLOW_ENGINE_RPC_CLIENT": "COMMON"}):
            with self.assertRaises(RpcFailure):
                RpcClient.from_environment(config)

    def test_response_environment_and_timeout(self):
        with self.assertRaises(RpcFailure) as error:
            self.client.resolve(self.owner, "bad-env", "resolve")
        self.assertEqual(error.exception.code, "RPC_RELEASE_MISMATCH")
        short = RpcClient(f"127.0.0.1:{self.port}", loopback_plaintext=True, timeout=0.02)
        try:
            with self.assertRaises(RpcFailure) as error:
                short.execute(self.owner, "asset", {}, "timeout")
            self.assertEqual(error.exception.code, "RPC_TIMEOUT_OUTCOME_UNKNOWN")
            self.assertEqual(self.fixture.calls, 1)
        finally:
            short.close()


if __name__ == "__main__":
    unittest.main()
