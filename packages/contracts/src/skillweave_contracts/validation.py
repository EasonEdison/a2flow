from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import NoReturn


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One stable, machine-readable contract validation failure."""

    path: str
    code: str
    message: str


class ContractValidationError(ValueError):
    """Raised when decoded input does not match an approved contract definition."""

    def __init__(self, issues: Iterable[ValidationIssue]) -> None:
        normalized = tuple(issues)
        if not normalized:
            raise ValueError("ContractValidationError requires at least one issue")
        if not all(isinstance(item, ValidationIssue) for item in normalized):
            raise TypeError("ContractValidationError issues must be ValidationIssue values")
        self._issues = normalized
        super().__init__("; ".join(f"{item.path}: {item.message}" for item in normalized))

    @property
    def issues(self) -> tuple[ValidationIssue, ...]:
        return self._issues


def fail(path: str, code: str, message: str) -> NoReturn:
    raise ContractValidationError((ValidationIssue(path=path, code=code, message=message),))


def require_object(
    value: object,
    *,
    path: str,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> dict[str, object]:
    if not isinstance(value, dict):
        fail(path, "invalid_type", "expected an object")
    keys = set(value)
    if not all(isinstance(key, str) for key in keys):
        fail(path, "invalid_key_type", "object keys must be strings")
    missing = sorted(required - keys)
    if missing:
        fail(path, "missing_field", f"missing required fields: {', '.join(missing)}")
    extra = sorted(keys - required - optional)
    if extra:
        fail(path, "extra_field", f"unexpected fields: {', '.join(extra)}")
    return value


def require_array(value: object, *, path: str) -> list[object]:
    if not isinstance(value, list):
        fail(path, "invalid_type", "expected an array")
    return value


def require_string(
    value: object,
    *,
    path: str,
    min_length: int = 0,
    max_length: int | None = None,
) -> str:
    if not isinstance(value, str):
        fail(path, "invalid_type", "expected a string")
    if len(value) < min_length:
        fail(path, "too_short", f"minimum length is {min_length}")
    if max_length is not None and len(value) > max_length:
        fail(path, "too_long", f"maximum length is {max_length}")
    return value


def require_integer(value: object, *, path: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        fail(path, "invalid_type", "expected an integer")
    if minimum is not None and value < minimum:
        fail(path, "out_of_range", f"minimum value is {minimum}")
    return value


def require_enum(value: object, *, path: str, allowed: frozenset[str]) -> str:
    parsed = require_string(value, path=path)
    if parsed not in allowed:
        fail(path, "invalid_value", f"expected one of: {', '.join(sorted(allowed))}")
    return parsed
