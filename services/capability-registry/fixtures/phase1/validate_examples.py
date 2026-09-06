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
ALLOWED_POLICY_KINDS = {"JSON_POINTER_EQUALS", "SCHEMA_VALID"}
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
    policies = ability_definition["successPolicies"]
    policy_ids = {policy["policyId"] for policy in policies}
    require(ability_definition["defaultSuccessPolicyRef"] in policy_ids, "default success policy missing")
    for policy in policies:
        require(policy["rule"]["kind"] in ALLOWED_POLICY_KINDS, "unsupported success policy kind")

    cases = payload["cases"]
    require(len(cases) == 6, "expected six bounded cases")
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

    timeout = by_id["adapter_timeout_without_platform_retry"]["result"]
    require(timeout["adapterCalled"] is True, "timeout must record dispatched adapter")
    require(timeout["runtimeRetryCount"] == 0, "timeout must not trigger Runtime business retry")

    forbidden_fragments = (" bearer ", ".corp.", "password=", "secret=", "token=")
    for value in walk_strings(payload):
        lowered = " %s " % value.lower()
        require(not any(fragment in lowered for fragment in forbidden_fragments), "sensitive-looking fixture value")
        if value.startswith("http://") or value.startswith("https://"):
            require(value in ALLOWED_REFERENCE_URIS, "fixture contains external endpoint")

    print("PASS baseline=SW-P1-20260907.2 cases=6")
    print("PASS trusted_fields_hidden pre_call_failures_closed runtime_business_retries=0")
    print("NOTE provisional_fixture_only runtime_evidence=false")


if __name__ == "__main__":
    main()
