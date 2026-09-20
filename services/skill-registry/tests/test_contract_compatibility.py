from __future__ import unicode_literals

import hashlib
import unittest

from skillweave_contracts import (
    ContractValidationError,
    UseSkillRequest as ContractUseSkillRequest,
    UseSkillResult,
)

from skill_registry.ports import MaterialPort, SkillMaterial
from skill_registry.resources import PackageEntry, PackageEntryDescriptor
from skill_registry.use_skill import (
    InvocationScope,
    TrustedContext,
    TrustedInvocationContext,
    TrustedResolutionEvidence,
    UseSkillRequest,
    use_skill,
)


def sha256_digest(content):
    return "sha256:" + hashlib.sha256(content).hexdigest()


class StaticMaterialPort(MaterialPort):

    def __init__(self, material):
        self.material = material

    def load_skill(self, skill_key, trusted_context):
        return self.material


class UseSkillContractCompatibilityTest(unittest.TestCase):

    def test_projected_result_round_trips_through_shared_contract_model(self):
        payload = "证据".encode("utf-8")
        material = SkillMaterial(
            instruction_entry=PackageEntry(
                descriptor=PackageEntryDescriptor(
                    handle_id="skill-instructions",
                    logical_path="SKILL.md",
                    media_type="text/markdown",
                    declared_byte_size=len(b"Summarize verified evidence."),
                    declared_content_digest=sha256_digest(
                        b"Summarize verified evidence."
                    ),
                ),
                content=b"Summarize verified evidence.",
            ),
            resource_entries=(
                PackageEntry(
                    descriptor=PackageEntryDescriptor(
                        handle_id="material-1",
                        logical_path="references/evidence.md",
                        media_type="text/markdown",
                        declared_byte_size=len(payload),
                        declared_content_digest=sha256_digest(payload),
                    ),
                    content=payload,
                ),
            ),
            required_tool_names=("execute_ability",),
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
        context = TrustedInvocationContext(
            contract_revision="SW-CONTRACTS-P1-CANDIDATE.1",
            trusted_context=TrustedContext(
                user_id=123,
                environment="PRT",
            ),
            invocation_scope=InvocationScope(
                kind="CONVERSATION",
                conversation_id="conversation-1",
            ),
            control_request_id="control-1",
        )

        result = use_skill(
            UseSkillRequest(skill_key="demo/evidence-first-brief"),
            context,
            StaticMaterialPort(material),
        )

        contract_request = ContractUseSkillRequest.from_mapping(
            {"skillKey": "demo/evidence-first-brief"}
        )
        self.assertEqual(
            "demo/evidence-first-brief",
            contract_request.skill_key,
        )
        with self.assertRaises(ContractValidationError):
            ContractUseSkillRequest.from_mapping({
                "skillKey": "demo/evidence-first-brief",
                "userId": "model-user",
                "environment": "ONLINE",
            })

        self.assertIsInstance(result, UseSkillResult)
        contract_result = UseSkillResult.from_mapping(result.to_mapping())
        self.assertEqual(result, contract_result)

        defensive_copy = contract_result.to_mapping()
        defensive_copy["content"]["resources"][0]["logicalPath"] = "changed.md"
        self.assertEqual(
            "references/evidence.md",
            contract_result.content.resources[0].logical_path,
        )


if __name__ == "__main__":
    unittest.main()
