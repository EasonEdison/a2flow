"""Shared PostgreSQL authentication admission, with an explicit proxy boundary."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import math
import uuid
from dataclasses import dataclass
from typing import Callable, Mapping

_LOGGER = logging.getLogger(__name__)
_ACTIONS = {"login": 1, "register": 2}


class AccountGuardError(Exception):
    def __init__(self, code: str, status: int, *, retry_after: int | None = None,
                 reference: str | None = None) -> None:
        super().__init__(code)
        self.code, self.status = code, status
        self.retry_after, self.reference = retry_after, reference

    def headers(self) -> dict[str, str]:
        headers = {"Cache-Control": "no-store"}
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        if self.reference is not None:
            headers["X-Request-ID"] = self.reference
        return headers


@dataclass(frozen=True)
class AdmissionPolicy:
    window_seconds: int
    global_limit: int
    ip_limit: int
    username_limit: int


@dataclass(frozen=True)
class AccountGuardConfig:
    login: AdmissionPolicy = AdmissionPolicy(60, 100, 20, 8)
    register: AdmissionPolicy = AdmissionPolicy(3600, 30, 5, 3)
    trusted_proxies: tuple[str, ...] = ()
    registration_enabled: bool = True

    @classmethod
    def from_environment(cls, values: Mapping[str, str]) -> AccountGuardConfig:
        def policy(action: str, defaults: AdmissionPolicy) -> AdmissionPolicy:
            fields = {}
            for name in ("window_seconds", "global_limit", "ip_limit", "username_limit"):
                key = "A2FLOW_AUTH_" + action.upper() + "_" + name.upper()
                raw = values.get(key, str(getattr(defaults, name)))
                if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= 86400:
                    raise RuntimeError("INVALID_AUTH_GUARD_CONFIGURATION:" + key)
                fields[name] = int(raw)
            return AdmissionPolicy(**fields)
        proxies = []
        for raw in values.get("A2FLOW_AUTH_TRUSTED_PROXIES", "").split(","):
            if not raw.strip():
                continue
            try:
                proxies.append(str(ipaddress.ip_address(raw.strip())))
            except ValueError:
                raise RuntimeError("INVALID_AUTH_TRUSTED_PROXY") from None
        enabled = values.get("A2FLOW_REGISTRATION_ENABLED", "true")
        if enabled not in {"true", "false"}:
            raise RuntimeError("INVALID_REGISTRATION_CONFIGURATION")
        return cls(policy("login", AdmissionPolicy(60, 100, 20, 8)),
                   policy("register", AdmissionPolicy(3600, 30, 5, 3)),
                   tuple(proxies), enabled == "true")


def client_address(scope: dict, trusted_proxies: tuple[str, ...]) -> str:
    peer = scope.get("client")
    try:
        address = str(ipaddress.ip_address(peer[0])) if peer else None
    except (ValueError, TypeError, IndexError):
        address = None
    if address is None:
        raise AccountGuardError("AUTH_CLIENT_ADDRESS_REQUIRED", 400)
    if address not in trusted_proxies:
        return address
    forwarded = [value for key, value in scope.get("headers", ())
                 if key.lower() == b"x-a2flow-client-ip"]
    if len(forwarded) != 1:
        raise AccountGuardError("AUTH_CLIENT_ADDRESS_REQUIRED", 400)
    try:
        return str(ipaddress.ip_address(forwarded[0].decode("ascii")))
    except (UnicodeError, ValueError):
        raise AccountGuardError("AUTH_CLIENT_ADDRESS_REQUIRED", 400) from None


class PostgresAccountGuard:
    def __init__(self, connection_factory: Callable, *, pepper: str,
                 environment: str, config: AccountGuardConfig) -> None:
        if environment not in {"PRT", "ONLINE"} or not pepper:
            raise ValueError("INVALID_AUTH_GUARD_CONFIGURATION")
        self._factory = connection_factory
        self._key = pepper.encode("utf-8")
        self.environment, self.config = environment, config

    @staticmethod
    def unavailable(operation: str, error: Exception) -> AccountGuardError:
        reference = uuid.uuid4().hex
        _LOGGER.error("AUTH_GUARD_UNAVAILABLE operation=%s reference=%s error_type=%s",
                      operation, reference, type(error).__name__)
        return AccountGuardError("AUTH_GUARD_UNAVAILABLE", 503, reference=reference)

    def check_ready(self) -> None:
        try:
            with self._factory() as connection:
                connection.execute("SELECT environment, action, address_key, username_key, "
                                   "created_at FROM account_auth_attempts LIMIT 0")
        except Exception as error:
            raise self.unavailable("readiness", error) from None

    def _digest(self, kind: str, value: str) -> str:
        return hmac.new(self._key, (kind + "\x00" + value).encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def admit(self, action: str, username: str, scope: dict) -> None:
        if action not in _ACTIONS:
            raise ValueError("INVALID_AUTH_ACTION")
        if action == "register" and not self.config.registration_enabled:
            raise AccountGuardError("REGISTRATION_DISABLED", 403)
        address = client_address(scope, self.config.trusted_proxies)
        address_key = self._digest("address", address)
        username_key = self._digest("username", username.casefold())
        policy = getattr(self.config, action)
        lock_key = (1 if self.environment == "PRT" else 2) * 10 + _ACTIONS[action]
        retry_after = 0
        try:
            with self._factory() as connection:
                # One short transaction serializes every process sharing this budget.
                # Password verification happens only after this transaction commits.
                connection.execute("SELECT pg_advisory_xact_lock(17324389, %s)", (lock_key,))
                current = connection.execute("SELECT clock_timestamp() AS current").fetchone()["current"]
                connection.execute(
                    "DELETE FROM account_auth_attempts WHERE environment=%s AND action=%s "
                    "AND created_at <= %s - (%s * interval '1 second')",
                    (self.environment, action, current, policy.window_seconds))
                row = connection.execute(
                    "SELECT count(*) AS total, min(created_at) AS first_total, "
                    "count(*) FILTER (WHERE address_key=%s) AS address_count, "
                    "min(created_at) FILTER (WHERE address_key=%s) AS first_address, "
                    "count(*) FILTER (WHERE username_key=%s) AS username_count, "
                    "min(created_at) FILTER (WHERE username_key=%s) AS first_username "
                    "FROM account_auth_attempts WHERE environment=%s AND action=%s",
                    (address_key, address_key, username_key, username_key,
                     self.environment, action)).fetchone()
                for count, first, limit in (("total", "first_total", policy.global_limit),
                                           ("address_count", "first_address", policy.ip_limit),
                                           ("username_count", "first_username", policy.username_limit)):
                    if row[count] >= limit:
                        retry_after = max(retry_after, max(1, math.ceil(
                            policy.window_seconds - (current - row[first]).total_seconds())))
                if not retry_after:
                    connection.execute(
                        "INSERT INTO account_auth_attempts "
                        "(environment, action, address_key, username_key, created_at) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (self.environment, action, address_key, username_key, current))
        except Exception as error:
            raise self.unavailable(action, error) from None
        if retry_after:
            raise AccountGuardError("AUTH_RATE_LIMITED", 429, retry_after=retry_after)
