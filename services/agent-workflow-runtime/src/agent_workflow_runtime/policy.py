"""One Runtime evaluator for the approved success-policy subset."""

import math

from jsonpointer import JsonPointerException, resolve_pointer
from skillweave_contracts.models import JsonPointerEqualsPolicy, SchemaValidPolicy

from .models import ActionConfig


def business_succeeded(config: ActionConfig, result: object) -> bool:
    """Require output validation before policy evaluation; missing is not JSON null."""
    if config.validate_result(result) is not True:
        return False
    policy = config.success_policy
    if isinstance(policy, SchemaValidPolicy):
        return True
    if not isinstance(policy, JsonPointerEqualsPolicy):
        raise ValueError("unsupported success policy")
    try:
        actual = resolve_pointer(result, policy.json_pointer)
    except JsonPointerException:
        return False
    expected = policy.expected_literal
    # JSON boolean and numeric domains differ even though Python True == 1.
    if isinstance(expected, bool) or expected is None:
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, (int, float)):
        return (
            type(actual) in (int, float)
            and math.isfinite(actual)
            and actual == expected
        )
    return type(actual) is str and actual == expected
