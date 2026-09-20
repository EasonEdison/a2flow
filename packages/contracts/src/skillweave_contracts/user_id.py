"""Long user IDs: strict backend integers, lossless decimal wire encoding.

Transport decoding belongs at trusted ingress, never inside model arguments.
This module does not confer authority on the identity being decoded.
"""

import re

MIN_USER_ID = -(1 << 63)
MAX_USER_ID = (1 << 63) - 1
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*|-[1-9][0-9]*)", re.ASCII)


def require_user_id(value: object) -> int:
    """Accept exactly an int in the signed64 range (not bool/float/string)."""
    if type(value) is not int or not MIN_USER_ID <= value <= MAX_USER_ID:
        raise ValueError("INVALID_LONG_USER_ID")
    return value


def user_id_from_wire(value: object) -> int:
    """Decode a JSON integer or canonical decimal text without coercive parsing."""
    if type(value) is int:
        return require_user_id(value)
    if (type(value) is not str or len(value) > 20
            or _DECIMAL.fullmatch(value) is None):
        raise ValueError("INVALID_LONG_USER_ID")
    return require_user_id(int(value))


def user_id_to_wire(value: int) -> str:
    """Browser JSON and HTTP headers must not round a64-bit ID via JS Number."""
    return str(require_user_id(value))
