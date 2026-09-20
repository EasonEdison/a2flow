from __future__ import unicode_literals

import hashlib
import unittest

import skill_registry
from skillweave_contracts import (
    ContractValidationError,
    UseSkillResult,
)
from skill_registry.ports import CatalogPort, MaterialPort, SkillMaterial
from skill_registry.resources import (
    PackageEntry,
    PackageEntryDescriptor,
    ResourceValidationError,
    ResourceLimits,
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
            instruction_entry=package_entry(
                "SKILL.md",
                b"Use the evidence, then write a concise brief.",
                handle_id="skill-instructions",
            ),
            resource_entries=(
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
                user_id=123,
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
        result_mapping = result.to_mapping()

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
            result_mapping,
        )
        self.assertNotIn("content", result_mapping["content"]["resources"][0])
        self.assertNotIn("text", result_mapping["content"]["resources"][0])

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
        self.assertNotIn("requiredToolNames", chat_result.to_mapping()["content"])

    def test_online_stable_and_gray_selection_use_shared_contract(self):
        context = self.context(
            InvocationScope(kind="CONVERSATION", conversation_id="conversation-1"),
            "control-online",
        )._replace(
            trusted_context=TrustedContext(
                user_id=123,
                environment="ONLINE",
            )
        )
        for selection in ("ONLINE_STABLE", "ONLINE_GRAY"):
            with self.subTest(selection=selection):
                evidence = self.material().resolution_evidence._replace(
                    environment="ONLINE",
                    selection=selection,
                )
                material = self.material()._replace(
                    resolution_evidence=evidence
                )

                result = use_skill(
                    UseSkillRequest(
                        skill_key="demo/evidence-first-brief"
                    ),
                    context,
                    FakeMaterialPort(material),
                )

                self.assertEqual("ONLINE", result.artifact.environment)
                self.assertEqual(selection, result.artifact.selection)

        invalid_evidence = self.material().resolution_evidence._replace(
            selection="ONLINE_STABLE"
        )
        with self.assertRaises(SkillRegistryValidationError) as raised:
            use_skill(
                UseSkillRequest(skill_key="demo/evidence-first-brief"),
                self.context(
                    InvocationScope(
                        kind="CONVERSATION",
                        conversation_id="conversation-1",
                    ),
                    "control-prt",
                ),
                FakeMaterialPort(
                    self.material()._replace(
                        resolution_evidence=invalid_evidence
                    )
                ),
            )
        self.assertEqual(
            "INVALID_RESOLUTION_EVIDENCE",
            raised.exception.code,
        )

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

    def test_required_tool_hints_must_be_unique(self):
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

    def test_tool_hints_and_script_paths_remain_inert_metadata(self):
        instructions = (
            b"Use execute_ability; scripts/setup.sh is reference material only."
        )
        script_reference = b"echo not executed"
        material = self.material(
            required_tool_names=("execute_ability",)
        )._replace(
            instruction_entry=package_entry(
                "SKILL.md",
                instructions,
                handle_id="skill-instructions",
            ),
            resource_entries=(
                package_entry(
                    "scripts/setup.sh",
                    script_reference,
                    handle_id="script-reference",
                ),
            ),
        )
        context = self.context(
            InvocationScope(kind="CONVERSATION", conversation_id="conversation-1"),
            "control-inert",
        )

        result = use_skill(
            UseSkillRequest(skill_key="demo/evidence-first-brief"),
            context,
            FakeMaterialPort(material),
        ).to_mapping()

        self.assertEqual(
            instructions.decode("utf-8"),
            result["content"]["instructions"],
        )
        self.assertEqual(
            ["execute_ability"],
            result["content"]["requiredToolNames"],
        )
        resource = result["content"]["resources"][0]
        self.assertEqual("scripts/setup.sh", resource["logicalPath"])
        self.assertEqual(
            {
                "handleId",
                "accessMode",
                "logicalPath",
                "mediaType",
                "byteSize",
                "contentDigest",
            },
            set(resource),
        )
        for forbidden_field in ("content", "text", "execute", "authorization"):
            self.assertNotIn(forbidden_field, resource)

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
        self.assertIs(UseSkillResult, skill_registry.UseSkillResult)
        self.assertIs(MaterialPort, skill_registry.MaterialPort)
        self.assertIs(use_skill, skill_registry.use_skill)

    def test_rejects_line_breaks_in_contract_pattern_fields(self):
        context = self.context(
            InvocationScope(kind="CONVERSATION", conversation_id="conversation-1"),
            "control-1",
        )
        evidence = self.material().resolution_evidence

        for line_break in ("\n", "\r", "\r\n"):
            with self.subTest(field="skillKey", line_break=repr(line_break)):
                with self.assertRaises(ContractValidationError) as raised:
                    UseSkillRequest(
                        skill_key="demo/evidence-first-brief" + line_break
                    )
                self.assertEqual(
                    {"invalid_skill_key"},
                    {issue.code for issue in raised.exception.issues},
                )

            with self.subTest(field="userId", line_break=repr(line_break)):
                invalid_context = context._replace(
                    trusted_context=TrustedContext(
                        user_id="123" + line_break,
                        environment="PRT",
                    )
                )
                with self.assertRaises(
                        SkillRegistryValidationError) as raised:
                    use_skill(
                        UseSkillRequest(
                            skill_key="demo/evidence-first-brief"
                        ),
                        invalid_context,
                        FakeMaterialPort(self.material()),
                    )
                self.assertEqual(
                    "INVALID_TRUSTED_CONTEXT",
                    raised.exception.code,
                )

            with self.subTest(
                    field="contentDigest",
                    line_break=repr(line_break)):
                material = self.material()._replace(
                    resolution_evidence=evidence._replace(
                        content_digest=evidence.content_digest + line_break
                    )
                )
                with self.assertRaises(
                        SkillRegistryValidationError) as raised:
                    use_skill(
                        UseSkillRequest(
                            skill_key="demo/evidence-first-brief"
                        ),
                        context,
                        FakeMaterialPort(material),
                    )
                self.assertEqual(
                    "INVALID_RESOLUTION_EVIDENCE",
                    raised.exception.code,
                )

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

    def test_instructions_are_a_verified_bounded_skill_entry(self):
        context = self.context(
            InvocationScope(kind="CONVERSATION", conversation_id="conversation-1"),
            "control-1",
        )
        valid_instruction = self.material().instruction_entry
        cases = (
            (
                "DECLARED_DIGEST_MISMATCH",
                valid_instruction._replace(
                    descriptor=valid_instruction.descriptor._replace(
                        declared_content_digest=sha256_digest(b"different")
                    )
                ),
                ResourceLimits(),
            ),
            (
                "INVALID_TEXT_ENCODING",
                package_entry(
                    "SKILL.md",
                    b"\xff",
                    handle_id="skill-instructions",
                ),
                ResourceLimits(),
            ),
            (
                "ENTRY_BYTES_LIMIT_EXCEEDED",
                valid_instruction,
                ResourceLimits(
                    max_entry_bytes=8,
                    max_total_bytes=16,
                ),
            ),
        )
        for expected_code, instruction_entry, limits in cases:
            with self.subTest(expected_code=expected_code):
                material = self.material()._replace(
                    instruction_entry=instruction_entry
                )
                with self.assertRaises(ResourceValidationError) as raised:
                    use_skill(
                        UseSkillRequest(
                            skill_key="demo/evidence-first-brief"
                        ),
                        context,
                        FakeMaterialPort(material),
                        resource_limits=limits,
                    )
                self.assertEqual(expected_code, raised.exception.code)

        with self.assertRaises(ResourceValidationError) as raised:
            use_skill(
                UseSkillRequest(skill_key="demo/evidence-first-brief"),
                context,
                FakeMaterialPort(self.material()),
                resource_limits=ResourceLimits(max_entries=1),
            )
        self.assertEqual("ENTRY_COUNT_LIMIT_EXCEEDED", raised.exception.code)

        with self.assertRaises(SkillRegistryValidationError) as raised:
            use_skill(
                UseSkillRequest(skill_key="demo/evidence-first-brief"),
                context,
                FakeMaterialPort(
                    self.material()._replace(instruction_entry=None)
                ),
            )
        self.assertEqual("INVALID_SKILL_MATERIAL", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
