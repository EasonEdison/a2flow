from __future__ import unicode_literals

import hashlib
import unittest

import skill_registry
from skill_registry.ports import CatalogPort, MaterialPort, SkillMaterial
from skill_registry.resources import (
    PackageEntry,
    PackageEntryDescriptor,
    ResourceValidationError,
)
from skill_registry.use_skill import (
    InvocationScope,
    SkillRegistryValidationError,
    TrustedContext,
    TrustedInvocationContext,
    TrustedResolutionEvidence,
    UseSkillRequest,
    use_skill,
)


def sha256_digest(content):
    return "sha256:" + hashlib.sha256(content).hexdigest()


def package_entry(logical_path, content, handle_id="material-1"):
    return PackageEntry(
        descriptor=PackageEntryDescriptor(
            handle_id=handle_id,
            logical_path=logical_path,
            media_type="text/markdown",
            declared_byte_size=len(content),
            declared_content_digest=sha256_digest(content),
        ),
        content=content,
    )


class FakeMaterialPort(MaterialPort):

    def __init__(self, material):
        self.material = material
        self.calls = []

    def load_skill(self, skill_key, trusted_context):
        self.calls.append((skill_key, trusted_context))
        return self.material


class UseSkillTest(unittest.TestCase):

    def material(self, required_tool_names=("execute_ability",)):
        return SkillMaterial(
            instructions="Use the evidence, then write a concise brief.",
            entries=(
                package_entry(
                    "references/source.md",
                    "可信材料".encode("utf-8"),
                ),
            ),
            required_tool_names=required_tool_names,
            resolution_evidence=TrustedResolutionEvidence(
                skill_key="demo/evidence-first-brief",
                asset_id="skill-evidence-first-brief",
                version_id="version-20260907",
                content_digest=sha256_digest(b"canonical-package"),
                environment="PRT",
                selection="PRT_CURRENT",
                evidence_ref="evidence-20260907",
            ),
        )

    def context(self, scope, control_request_id):
        return TrustedInvocationContext(
            contract_revision="SW-CONTRACTS-P1-CANDIDATE.1",
            trusted_context=TrustedContext(
                user_id="user-123",
                environment="PRT",
            ),
            invocation_scope=scope,
            control_request_id=control_request_id,
        )

    def test_maps_verified_material_and_trusted_evidence_to_contract_shape(self):
        port = FakeMaterialPort(self.material())
        context = self.context(
            InvocationScope(kind="CONVERSATION", conversation_id="conversation-1"),
            "control-1",
        )

        result = use_skill(
            UseSkillRequest(skill_key="demo/evidence-first-brief"),
            context,
            port,
        )

        self.assertEqual(
            [("demo/evidence-first-brief", context.trusted_context)],
            port.calls,
        )
        self.assertEqual(
            {
                "contractRevision": "SW-CONTRACTS-P1-CANDIDATE.1",
                "content": {
                    "instructions": "Use the evidence, then write a concise brief.",
                    "resources": [
                        {
                            "handleId": "material-1",
                            "accessMode": "READ_ONLY",
                            "logicalPath": "references/source.md",
                            "mediaType": "text/markdown",
                            "byteSize": len("可信材料".encode("utf-8")),
                            "contentDigest": sha256_digest(
                                "可信材料".encode("utf-8")
                            ),
                        },
                    ],
                    "requiredToolNames": ["execute_ability"],
                },
                "artifact": {
                    "skillKey": "demo/evidence-first-brief",
                    "resolvedVersion": {
                        "asset": {
                            "assetType": "SKILL",
                            "assetId": "skill-evidence-first-brief",
                        },
                        "versionId": "version-20260907",
                    },
                    "contentDigest": sha256_digest(b"canonical-package"),
                    "environment": "PRT",
                    "selection": "PRT_CURRENT",
                    "evidenceRef": "evidence-20260907",
                },
            },
            result,
        )
        self.assertNotIn("content", result["content"]["resources"][0])
        self.assertNotIn("text", result["content"]["resources"][0])

    def test_chat_and_workflow_reuse_same_verified_material(self):
        request = UseSkillRequest(skill_key="demo/evidence-first-brief")
        chat_port = FakeMaterialPort(self.material(required_tool_names=()))
        workflow_port = FakeMaterialPort(self.material(required_tool_names=()))
        chat_context = self.context(
            InvocationScope(kind="CONVERSATION", conversation_id="conversation-1"),
            "control-chat",
        )
        workflow_context = self.context(
            InvocationScope(
                kind="WORKFLOW",
                run_id="run-1",
                node_id="node-1",
            ),
            "control-workflow",
        )

        chat_result = use_skill(request, chat_context, chat_port)
        workflow_result = use_skill(request, workflow_context, workflow_port)

        self.assertEqual(chat_result, workflow_result)
        self.assertNotIn("requiredToolNames", chat_result["content"])

    def test_rejects_model_override_and_untrusted_evidence_mismatch(self):
        with self.assertRaises(TypeError):
            UseSkillRequest(
                skill_key="demo/evidence-first-brief",
                user_id="model-user",
                environment="ONLINE",
            )

        mismatches = (
            TrustedResolutionEvidence(
                skill_key="other/skill",
                asset_id="skill-evidence-first-brief",
                version_id="version-20260907",
                content_digest=sha256_digest(b"canonical-package"),
                environment="PRT",
                selection="PRT_CURRENT",
                evidence_ref="evidence-20260907",
            ),
            TrustedResolutionEvidence(
                skill_key="demo/evidence-first-brief",
                asset_id="skill-evidence-first-brief",
                version_id="version-20260907",
                content_digest=sha256_digest(b"canonical-package"),
                environment="ONLINE",
                selection="ONLINE_STABLE",
                evidence_ref="evidence-20260907",
            ),
        )
        context = self.context(
            InvocationScope(kind="CONVERSATION", conversation_id="conversation-1"),
            "control-1",
        )
        for evidence in mismatches:
            with self.subTest(evidence=evidence):
                material = self.material()._replace(resolution_evidence=evidence)
                with self.assertRaises(SkillRegistryValidationError):
                    use_skill(
                        UseSkillRequest(
                            skill_key="demo/evidence-first-brief"
                        ),
                        context,
                        FakeMaterialPort(material),
                    )

    def test_required_tools_are_unique_hints_only(self):
        material = self.material(
            required_tool_names=("execute_ability", "execute_ability")
        )
        context = self.context(
            InvocationScope(kind="CONVERSATION", conversation_id="conversation-1"),
            "control-1",
        )

        with self.assertRaises(SkillRegistryValidationError) as raised:
            use_skill(
                UseSkillRequest(skill_key="demo/evidence-first-brief"),
                context,
                FakeMaterialPort(material),
            )

        self.assertEqual("INVALID_REQUIRED_TOOL_NAMES", raised.exception.code)

    def test_ports_and_descriptors_are_abstract_or_immutable(self):
        with self.assertRaises(TypeError):
            CatalogPort()
        with self.assertRaises(TypeError):
            MaterialPort()

        request = UseSkillRequest(skill_key="demo/evidence-first-brief")
        with self.assertRaises(AttributeError):
            request.skill_key = "changed"

    def test_public_api_exports_the_bounded_domain_surface(self):
        self.assertIs(UseSkillRequest, skill_registry.UseSkillRequest)
        self.assertIs(MaterialPort, skill_registry.MaterialPort)
        self.assertIs(use_skill, skill_registry.use_skill)

    def test_rejects_crlf_in_approved_contract_pattern_fields(self):
        context = self.context(
            InvocationScope(kind="CONVERSATION", conversation_id="conversation-1"),
            "control-1",
        )

        with self.assertRaises(SkillRegistryValidationError) as raised:
            use_skill(
                UseSkillRequest(skill_key="demo/evidence-first-brief\n"),
                context,
                FakeMaterialPort(self.material()),
            )
        self.assertEqual("INVALID_SKILL_KEY", raised.exception.code)

        invalid_context = context._replace(
            trusted_context=TrustedContext(
                user_id="user-123\n",
                environment="PRT",
            )
        )
        with self.assertRaises(SkillRegistryValidationError) as raised:
            use_skill(
                UseSkillRequest(skill_key="demo/evidence-first-brief"),
                invalid_context,
                FakeMaterialPort(self.material()),
            )
        self.assertEqual("INVALID_TRUSTED_CONTEXT", raised.exception.code)

        evidence = self.material().resolution_evidence
        material = self.material()._replace(
            resolution_evidence=evidence._replace(
                content_digest=evidence.content_digest + "\n"
            )
        )
        with self.assertRaises(SkillRegistryValidationError) as raised:
            use_skill(
                UseSkillRequest(skill_key="demo/evidence-first-brief"),
                context,
                FakeMaterialPort(material),
            )
        self.assertEqual("INVALID_RESOLUTION_EVIDENCE", raised.exception.code)

    def test_rejects_falsy_invalid_resource_limits(self):
        context = self.context(
            InvocationScope(kind="CONVERSATION", conversation_id="conversation-1"),
            "control-1",
        )

        with self.assertRaises(ResourceValidationError) as raised:
            use_skill(
                UseSkillRequest(skill_key="demo/evidence-first-brief"),
                context,
                FakeMaterialPort(self.material()),
                resource_limits=0,
            )

        self.assertEqual("INVALID_LIMITS", raised.exception.code)



if __name__ == "__main__":
    unittest.main()
