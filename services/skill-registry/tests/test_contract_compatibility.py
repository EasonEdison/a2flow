from __future__ import unicode_literals

import hashlib
import json
import os
import sys
import unittest

from jsonschema import Draft4Validator, RefResolver

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


REPOSITORY_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
))
CONTRACTS_ROOT = os.path.join(REPOSITORY_ROOT, "packages", "contracts")
sys.path.insert(0, os.path.join(CONTRACTS_ROOT, "tests"))

from validate_contracts import semantic_errors  # noqa: E402


def sha256_digest(content):
    return "sha256:" + hashlib.sha256(content).hexdigest()


class StaticMaterialPort(MaterialPort):

    def __init__(self, material):
        self.material = material

    def load_skill(self, skill_key, trusted_context):
        return self.material


class UseSkillContractCompatibilityTest(unittest.TestCase):

    def test_projected_result_matches_approved_schema_and_semantics(self):
        payload = "证据".encode("utf-8")
        material = SkillMaterial(
            instructions="Summarize verified evidence.",
            entries=(
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
                user_id="user-123",
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

        schema_path = os.path.join(
            CONTRACTS_ROOT,
            "schemas",
            "contracts-bundle.schema.json",
        )
        with open(schema_path, "r") as handle:
            schema = json.load(handle)
        validator = Draft4Validator(
            {"$ref": "#/definitions/useSkillResult"},
            resolver=RefResolver.from_schema(schema),
        )
        errors = sorted(
            validator.iter_errors(result),
            key=lambda item: list(item.path),
        )
        self.assertEqual([], [error.message for error in errors])
        self.assertEqual([], semantic_errors("useSkillResult", result))


if __name__ == "__main__":
    unittest.main()
