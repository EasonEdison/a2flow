from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


APPROVED_DEFINITION_NAMES = frozenset(
    {
        "contractRevision",
        "identifier",
        "longUserId",
        "trustedContext",
        "trustedInvocationContext",
        "invocationScope",
        "useSkillRequest",
        "skillKey",
        "useSkillResult",
        "useSkillContent",
        "useSkillArtifact",
        "authorizedMaterialHandle",
        "skillAssetVersionRef",
        "resultInterpretationPolicy",
        "resultInterpretationPolicySet",
    }
)

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "contracts-bundle.schema.json"


def load_approved_schema() -> dict[str, Any]:
    """Load the released closure from the neutral schema source of truth."""

    with _SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        source = json.load(handle)
    definitions = source.get("definitions")
    if not isinstance(definitions, dict):
        raise ValueError("contract schema has no definitions object")
    missing = APPROVED_DEFINITION_NAMES - set(definitions)
    if missing:
        raise ValueError(f"contract schema is missing approved definitions: {sorted(missing)}")
    approved = {name: copy.deepcopy(definitions[name]) for name in sorted(APPROVED_DEFINITION_NAMES)}
    result = {
        key: copy.deepcopy(value)
        for key, value in source.items()
        if key != "definitions"
    }
    result["definitions"] = approved
    return result


def load_definition_schema(definition_name: str) -> dict[str, Any]:
    """Load a self-contained root schema for one approved external definition."""

    if definition_name not in APPROVED_DEFINITION_NAMES:
        raise KeyError(f"definition is not approved for this package: {definition_name}")
    schema = load_approved_schema()
    schema["$ref"] = f"#/definitions/{definition_name}"
    return schema
