from __future__ import print_function

import json
import os
import sys

from jsonschema import Draft4Validator, RefResolver


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(ROOT, "schemas", "contracts-bundle.schema.json")
CASES_PATH = os.path.join(ROOT, "tests", "cases.json")


def load_json(path):
    with open(path, "r") as handle:
        return json.load(handle)


def semantic_errors(definition, fixture):
    errors = []

    if definition == "controlRequest":
        versions = fixture.get("recordedAssetVersions")
        if isinstance(versions, list):
            seen_assets = set()
            for version in versions:
                asset = version.get("asset", {}) if isinstance(version, dict) else {}
                key = (asset.get("assetType"), asset.get("assetId"))
                if None in key:
                    continue
                if key in seen_assets:
                    errors.append("recordedAssetVersions contains duplicate asset identity")
                    break
                seen_assets.add(key)

    if definition == "resultInterpretationPolicySet":
        policies = fixture.get("resultInterpretationPolicies")
        if isinstance(policies, list):
            refs = [
                policy.get("policyRef")
                for policy in policies
                if isinstance(policy, dict) and policy.get("policyRef") is not None
            ]
            if len(refs) != len(set(refs)):
                errors.append("resultInterpretationPolicies contains duplicate policyRef")
            default_ref = fixture.get("defaultSuccessPolicyRef")
            if default_ref is not None and default_ref not in refs:
                errors.append("defaultSuccessPolicyRef does not resolve")

    if definition == "useSkillResult":
        content = fixture.get("content", {})
        resources = content.get("resources") if isinstance(content, dict) else None
        if isinstance(resources, list):
            logical_paths = [
                resource.get("logicalPath")
                for resource in resources
                if isinstance(resource, dict) and resource.get("logicalPath") is not None
            ]
            if len(logical_paths) != len(set(logical_paths)):
                errors.append("resources contains duplicate logicalPath")

    return errors


def main():
    if not os.path.exists(SCHEMA_PATH):
        print("FAIL schema missing: {0}".format(SCHEMA_PATH))
        return 1

    bundle = load_json(SCHEMA_PATH)
    Draft4Validator.check_schema(bundle)
    resolver = RefResolver.from_schema(bundle)
    cases = load_json(CASES_PATH)
    failures = []

    for case in cases:
        fixture_path = os.path.join(ROOT, "tests", case["fixture"])
        fixture = load_json(fixture_path)
        if case["definition"] not in bundle.get("definitions", {}):
            detail = "definition missing: {0}".format(case["definition"])
            failures.append("{0}: {1}".format(case["name"], detail))
            print("FAIL {0}: {1}".format(case["name"], detail))
            continue
        validator = Draft4Validator(
            {"$ref": "#/definitions/{0}".format(case["definition"])},
            resolver=resolver,
        )
        schema_errors = sorted(
            validator.iter_errors(fixture),
            key=lambda item: list(item.path),
        )
        contract_errors = semantic_errors(case["definition"], fixture)
        actual_valid = not schema_errors and not contract_errors
        if actual_valid != case["expectedValid"]:
            if actual_valid:
                detail = "valid"
            elif schema_errors:
                detail = schema_errors[0].message
            else:
                detail = contract_errors[0]
            failures.append("{0}: {1}".format(case["name"], detail))
            print("FAIL {0}: {1}".format(case["name"], detail))
        else:
            print("PASS {0}".format(case["name"]))

    print("SUMMARY total={0} passed={1} failed={2}".format(
        len(cases), len(cases) - len(failures), len(failures)
    ))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
