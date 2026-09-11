"""DeepSeek-only config tests; no SDK request or credential lookup."""

import unittest

from agent_workflow_runtime.model_config import ModelConfigurationError, parse_deepseek_configuration
from agent_workflow_runtime.model_factory import DeepSeekModelFactory
from agent_workflow_runtime.models import ActionRejected
from support import context


class DeepSeekConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.raw = {"model_id": "deepseek-v4-pro", "credential_ref": "synthetic-secret-reference"}

    def test_one_route_explicit_models_and_public_options(self):
        config = parse_deepseek_configuration({**self.raw, "options": {
            "thinking": "enabled", "reasoning_effort": "high", "max_tokens": 512,
        }})
        self.assertEqual("deepseek:deepseek-v4-pro", config.harness_profile_key)
        self.assertEqual({"extra_body": {"thinking": {"type": "enabled"}},
                          "reasoning_effort": "high", "max_tokens": 512}, config.options.sdk_options())
        flash = parse_deepseek_configuration({**self.raw, "model_id": "deepseek-v4-flash"})
        self.assertEqual("deepseek:deepseek-v4-flash", flash.harness_profile_key)

    def test_unknown_fields_routes_options_and_embedded_secret_reject_before_secret_resolution(self):
        seen = []
        factory = DeepSeekModelFactory(lambda *args: self.raw, lambda *args: seen.append("secret"))
        original = dict(self.raw)
        for changes in (
            {"provider": "bailian"}, {"protocol": "unknown"}, {"model_id": "unknown"},
            {"endpoint": "https://unreviewed.example.test/v1"},
            {"endpoint": "https://user:PRIVATE-SECRET@api.deepseek.com"},
            {"options": {"temperature": 0.5}}, {"options": {"extra_body": {"unreviewed": True}}},
            {"options": {"thinking": "disabled", "reasoning_effort": "high"}},
            {"options": {"max_tokens": True}}, {"timeout_seconds": float("inf")},
            {"adapter_class": "untrusted.module.Class"},
        ):
            self.raw = {**original, **changes}
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ModelConfigurationError, "^INVALID_DEEPSEEK_CONFIGURATION$") as caught:
                    factory.create("logical-model", context().trusted_context)
                self.assertNotIn("PRIVATE", str(caught.exception))
                self.assertEqual([], seen)

    def test_repr_redacts_reference_and_options(self):
        config = parse_deepseek_configuration(self.raw)
        self.assertNotIn("synthetic-secret-reference", repr(config))
        self.assertNotIn("api.deepseek.com", repr(config))
        self.assertNotIn("options=", repr(config))

    def test_missing_owner_rejects_before_configuration_read(self):
        factory = DeepSeekModelFactory(lambda *args: self.fail("untrusted config read"), None)
        with self.assertRaisesRegex(ActionRejected, "TRUSTED_CONTEXT_REQUIRED"):
            factory.create("logical-model", None)

    def test_configuration_errors_are_sanitized_and_never_fall_back(self):
        def broken(*args):
            raise ValueError("PRIVATE-CONFIGURATION")
        factory = DeepSeekModelFactory(broken, lambda *args: self.fail("unexpected secret lookup"))
        with self.assertRaisesRegex(ModelConfigurationError, "^MODEL_CONSTRUCTION_FAILED$"):
            factory.create("logical-model", context().trusted_context)
