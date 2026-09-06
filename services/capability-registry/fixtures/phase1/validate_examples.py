"""Validate provisional execute_ability consumer examples with stdlib only.

This is a fixture invariant check, not a shared contract implementation and not
Runtime evidence.
"""

from __future__ import print_function

import json
from pathlib import Path


FIXTURE_PATH = Path(__file__).with_name("execute-ability.examples.json")
FORBIDDEN_MODEL_KEYS = {
    "authorizationContext",
    "credentialRef",
    "credentialRefs",
    "environment",
    "releaseRef",
    "releaseVersion",
    "userId",
}
PRE_CALL_FAILURES = {
    "ARGUMENT_INVALID",
    "AUTHORIZATION_DENIED",
    "CONFIG_VERSION_MISMATCH",
    "CREDENTIAL_UNAVAILABLE",
}
CONTRACT_REVISION = "SW-CONTRACTS-P1-CANDIDATE.1"
ALLOWED_POLICY_OPERATORS = {"JSON_POINTER_EQUALS", "SCHEMA_VALID"}
ALLOWED_REFERENCE_URIS = {
    "https://json-schema.org/draft/2020-12/schema",
}


def walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            for nested in walk_keys(child):
                yield nested
    elif isinstance(value, list):
        for item in value:
            for nested in walk_keys(item):
                yield nested


def walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            for nested in walk_strings(child):
                yield nested
    elif isinstance(value, list):
        for item in value:
            for nested in walk_strings(item):
                yield nested


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    with FIXTURE_PATH.open("r", encoding="utf-8") as fixture_file:
        payload = json.load(fixture_file)

    metadata = payload["fixtureMetadata"]
    require(metadata["baseline"] == "SW-P1-20260907.2", "baseline mismatch")
    require(metadata["status"] == "PROVISIONAL_CONSUMER_EXAMPLE", "fixture must remain provisional")
    require(metadata["synthetic"] is True, "fixture must be synthetic")
    require(metadata["runtimeEvidence"] is False, "fixture must not claim runtime evidence")

    ability_definition = payload["abilityDefinition"]
    policies = ability_definition["resultInterpretationPolicies"]
    policy_refs = [policy["policyRef"] for policy in policies]
    require(len(policy_refs) == len(set(policy_refs)), "policyRef must be unique")
    require(ability_definition["defaultSuccessPolicyRef"] in policy_refs, "default success policy missing")
    policies_by_ref = {policy["policyRef"]: policy for policy in policies}
    base_policy_keys = {"contractRevision", "operator", "policyRef"}
    equals_policy_keys = base_policy_keys.union({"expectedLiteral", "jsonPointer"})
    for policy in policies:
        require(policy["contractRevision"] == CONTRACT_REVISION, "contract revision mismatch")
        require(policy["operator"] in ALLOWED_POLICY_OPERATORS, "unsupported result policy operator")
        if policy["operator"] == "SCHEMA_VALID":
            require(set(policy) == base_policy_keys, "SCHEMA_VALID shape changed")
        else:
            require(set(policy) == equals_policy_keys, "JSON_POINTER_EQUALS shape changed")
            literal = policy["expectedLiteral"]
            require(literal is None or isinstance(literal, (bool, float, int, str)), "expectedLiteral must be primitive")

    rejected_policies = payload["rejectedPolicyDefinitions"]
    require(len(rejected_policies) == 2, "expected two rejected policy examples")
    for rejected in rejected_policies:
        require(rejected["policy"]["operator"] not in ALLOWED_POLICY_OPERATORS, "rejected operator became allowed")
        require(rejected["expectedErrorCode"] == "RESULT_POLICY_OPERATOR_UNSUPPORTED", "rejection code changed")

    cases = payload["cases"]
    require(len(cases) == 9, "expected nine bounded cases")
    require(len({case["caseId"] for case in cases}) == len(cases), "caseId must be unique")

    by_id = {}
    for case in cases:
        by_id[case["caseId"]] = case
        model_input = case["modelToolInput"]
        require(set(model_input) == {"abilityKey", "arguments"}, "model tool input surface changed")
        leaked = FORBIDDEN_MODEL_KEYS.intersection(set(walk_keys(model_input)))
        require(not leaked, "trusted keys leaked into model input: %s" % sorted(leaked))
        result = case["result"]
        require(result["runtimeRetryCount"] == 0, "platform business retry must remain zero")
        if result["status"] in PRE_CALL_FAILURES:
            require(result["adapterCalled"] is False, "pre-call failure invoked adapter")
        require("idempotencyKey" not in set(walk_keys(case)), "platform fixture must not claim business idempotency")
        require("actionCallSucceeded" not in result, "A2UI Action fact leaked into ability result")
        require("interactionCompleted" not in result, "A2UI completion fact leaked into ability result")
        if "interpretation" in result:
            interpretation = result["interpretation"]
            require(result["outputSchemaValidated"] is True, "policy evaluated before output schema validation")
            require(result["policyMatched"] is interpretation["matched"], "policy facts diverged")
            require(interpretation["policyRef"] in policy_refs, "interpretation policy missing from release")
            if "effectiveSuccessPolicyRef" in case:
                require(case["effectiveSuccessPolicyRef"] == interpretation["policyRef"], "effective policy ref diverged")

    prt = by_id["prt_current_success"]
    require(prt["trustedContext"]["environment"] == "PRT", "PRT trusted environment missing")
    require(prt["resolvedAbility"]["environment"] == "PRT", "PRT crossed environment")
    require(prt["resolvedAbility"]["servingTrack"] == "CURRENT", "PRT must use current")

    online = by_id["online_gray_success"]
    require(online["trustedContext"]["environment"] == "ONLINE", "ONLINE trusted environment missing")
    require(online["resolvedAbility"]["environment"] == "ONLINE", "ONLINE crossed environment")
    require(online["resolvedAbility"]["servingTrack"] == "GRAY_CANDIDATE", "ONLINE gray not selected")
    require("prt" not in online["resolvedAbility"]["releaseRef"].lower(), "ONLINE release points to PRT")

    mismatch = by_id["version_mismatch"]["result"]
    require(mismatch["adapterCalled"] is False, "version mismatch invoked adapter")
    require(mismatch["resetRequired"] is True, "version mismatch must require reset")

    denied = by_id["authorization_denied"]["result"]
    require(denied["adapterCalled"] is False, "authorization denial invoked adapter")

    business_failure = by_id["configured_success_not_matched"]["result"]
    require(business_failure["adapterCalled"] is True, "business result requires adapter call")
    require(business_failure["interpretation"]["matched"] is False, "success policy mismatch lost")

    missing_case = by_id["missing_pointer_fails_closed"]
    require("optionalValue" not in missing_case["adapterOutput"], "missing path fixture unexpectedly found value")
    require(missing_case["result"]["policyMatched"] is False, "missing path matched")
    require(missing_case["result"]["interpretation"]["reasonCode"] == "PATH_MISSING", "missing path reason lost")

    null_case = by_id["found_null_matches_null"]
    require("optionalValue" in null_case["adapterOutput"], "found null path missing")
    require(null_case["adapterOutput"]["optionalValue"] is None, "found null changed type")
    require(null_case["result"]["policyMatched"] is True, "found null did not match JSON null")

    strict_case = by_id["strict_type_mismatch"]
    observed_value = strict_case["adapterOutput"]["comparisonValue"]
    expected_value = policies_by_ref["numberOne"]["expectedLiteral"]
    require(type(observed_value) is not type(expected_value), "strict mismatch fixture uses same JSON type")
    require(strict_case["result"]["policyMatched"] is False, "implicit type conversion was applied")

    rejected_by_id = {item["caseId"]: item for item in rejected_policies}
    require(rejected_by_id["not_equals_operator_rejected"]["policy"]["operator"] == "NOT_EQUALS", "NOT_EQUALS rejection missing")

    timeout = by_id["adapter_timeout_without_platform_retry"]["result"]
    require(timeout["adapterCalled"] is True, "timeout must record dispatched adapter")
    require(timeout["runtimeRetryCount"] == 0, "timeout must not trigger Runtime business retry")

    forbidden_fragments = (" bearer ", ".corp.", "password=", "secret=", "token=")
    for value in walk_strings(payload):
        lowered = " %s " % value.lower()
        require(not any(fragment in lowered for fragment in forbidden_fragments), "sensitive-looking fixture value")
        if value.startswith("http://") or value.startswith("https://"):
            require(value in ALLOWED_REFERENCE_URIS, "fixture contains external endpoint")

    print("PASS baseline=SW-P1-20260907.2 contract=%s cases=9 rejected_policies=2" % CONTRACT_REVISION)
    print("PASS trusted_fields_hidden pre_call_failures_closed runtime_business_retries=0")
    print("PASS pointer_missing_closed found_null_distinct strict_json_types")
    print("NOTE provisional_fixture_only runtime_evidence=false")


if __name__ == "__main__":
    main()
