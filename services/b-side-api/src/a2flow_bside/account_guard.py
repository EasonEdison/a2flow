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
# 登录与注册使用不同预算; 日志只记录定位信息, 不输出认证内容。
_ACTIONS = {"login": 1, "register": 2}


# 限流错误携带重试时间和引用号, 供 HTTP 层统一投影。
class AccountGuardError(Exception):
    def __init__(self, code: str, status: int, *, retry_after: int | None = None,
                 reference: str | None = None) -> None:
        super().__init__(code)
        self.code, self.status = code, status
        self.retry_after, self.reference = retry_after, reference

    def headers(self) -> dict[str, str]:
        # 认证响应禁止缓存, 限流时明确返回可再次尝试的等待秒数。
        headers = {"Cache-Control": "no-store"}
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        if self.reference is not None:
            headers["X-Request-ID"] = self.reference
        return headers


@dataclass(frozen=True)
# 分别限制全局、来源地址和用户名, 避免单一维度被绕过。
class AdmissionPolicy:
    window_seconds: int
    global_limit: int
    ip_limit: int
    username_limit: int


@dataclass(frozen=True)
# 登录和注册各自配置窗口; 代理信任范围必须显式声明。
class AccountGuardConfig:
    login: AdmissionPolicy = AdmissionPolicy(60, 100, 20, 8)
    register: AdmissionPolicy = AdmissionPolicy(3600, 30, 5, 3)
    trusted_proxies: tuple[str, ...] = ()
    registration_enabled: bool = True

    @classmethod
    def from_environment(cls, values: Mapping[str, str]) -> AccountGuardConfig:
        # 环境配置只接受有界正整数, 启动时拒绝无效防护参数。
        def policy(action: str, defaults: AdmissionPolicy) -> AdmissionPolicy:
            fields = {}
            for name in ("window_seconds", "global_limit", "ip_limit", "username_limit"):
                # 按动作和字段拼接固定配置键, 不从请求选择防护规则。
                key = "A2FLOW_AUTH_" + action.upper() + "_" + name.upper()
                raw = values.get(key, str(getattr(defaults, name)))
                if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= 86400:
                    raise RuntimeError("INVALID_AUTH_GUARD_CONFIGURATION:" + key)
                fields[name] = int(raw)
            return AdmissionPolicy(**fields)
        # 代理地址逐项解析为标准 IP, 不能用任意字符串建立信任。
        proxies = []
        for raw in values.get("A2FLOW_AUTH_TRUSTED_PROXIES", "").split(","):
            if not raw.strip():
                continue
            try:
                proxies.append(str(ipaddress.ip_address(raw.strip())))
            except ValueError:
                raise RuntimeError("INVALID_AUTH_TRUSTED_PROXY") from None
        # 注册开关只接受明确布尔文本, 拼写错误不能默认为开放。
        enabled = values.get("A2FLOW_REGISTRATION_ENABLED", "true")
        if enabled not in {"true", "false"}:
            raise RuntimeError("INVALID_REGISTRATION_CONFIGURATION")
        return cls(policy("login", AdmissionPolicy(60, 100, 20, 8)),
                   policy("register", AdmissionPolicy(3600, 30, 5, 3)),
                   tuple(proxies), enabled == "true")


def client_address(scope: dict, trusted_proxies: tuple[str, ...]) -> str:
    # 连接对端默认就是客户端; 只有受信代理才允许提供原始地址。
    peer = scope.get("client")
    try:
        address = str(ipaddress.ip_address(peer[0])) if peer else None
    except (ValueError, TypeError, IndexError):
        address = None
    # 无法识别地址则拒绝认证准入, 不共享一个虚假的默认地址预算。
    if address is None:
        raise AccountGuardError("AUTH_CLIENT_ADDRESS_REQUIRED", 400)
    if address not in trusted_proxies:
        return address
    # 仅接受受信代理设置的唯一专用地址头, 拒绝多值和非法编码。
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
        # 预算按环境隔离, 摘要密钥必须存在, 避免明文记录地址和用户名。
        if environment not in {"PRT", "ONLINE"} or not pepper:
            raise ValueError("INVALID_AUTH_GUARD_CONFIGURATION")
        self._factory = connection_factory
        self._key = pepper.encode("utf-8")
        self.environment, self.config = environment, config

    @staticmethod
    def unavailable(operation: str, error: Exception) -> AccountGuardError:
        # 存储故障生成可关联引用号, 日志不泄露 SQL 或认证参数。
        reference = uuid.uuid4().hex
        _LOGGER.error("AUTH_GUARD_UNAVAILABLE operation=%s reference=%s error_type=%s",
                      operation, reference, type(error).__name__)
        return AccountGuardError("AUTH_GUARD_UNAVAILABLE", 503, reference=reference)

    # 启动时检查防护表可读, 防止缺表情况下开放无防护认证。
    def check_ready(self) -> None:
        try:
            with self._factory() as connection:
                connection.execute("SELECT environment, action, address_key, username_key, "
                                   "created_at FROM account_auth_attempts LIMIT 0")
        except Exception as error:
            raise self.unavailable("readiness", error) from None

    # 不同类型使用分隔前缀计算 HMAC, 避免地址与用户名混用摘要空间。
    def _digest(self, kind: str, value: str) -> str:
        return hmac.new(self._key, (kind + "\x00" + value).encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def admit(self, action: str, username: str, scope: dict) -> None:
        # 先检查动作及注册开关, 再计算当前请求对应的预算键。
        if action not in _ACTIONS:
            raise ValueError("INVALID_AUTH_ACTION")
        if action == "register" and not self.config.registration_enabled:
            raise AccountGuardError("REGISTRATION_DISABLED", 403)
        address = client_address(scope, self.config.trusted_proxies)
        # 用户名统一大小写后计数; 数据库只保存带密钥的摘要。
        address_key = self._digest("address", address)
        username_key = self._digest("username", username.casefold())
        policy = getattr(self.config, action)
        # 锁键按环境和动作划分, 多进程对同一预算串行准入。
        lock_key = (1 if self.environment == "PRT" else 2) * 10 + _ACTIONS[action]
        retry_after = 0
        try:
            with self._factory() as connection:
                # One short transaction serializes every process sharing this budget.
                # Password verification happens only after this transaction commits.
                connection.execute("SELECT pg_advisory_xact_lock(17324389, %s)", (lock_key,))
                # 使用数据库时间清理窗口记录, 避免应用实例时钟差异影响计数。
                current = connection.execute("SELECT clock_timestamp() AS current").fetchone()["current"]
                connection.execute(
                    "DELETE FROM account_auth_attempts WHERE environment=%s AND action=%s "
                    "AND created_at <= %s - (%s * interval '1 second')",
                    (self.environment, action, current, policy.window_seconds))
                # 同一事务统计三个维度的使用量及最早尝试时间。
                row = connection.execute(
                    "SELECT count(*) AS total, min(created_at) AS first_total, "
                    "count(*) FILTER (WHERE address_key=%s) AS address_count, "
                    "min(created_at) FILTER (WHERE address_key=%s) AS first_address, "
                    "count(*) FILTER (WHERE username_key=%s) AS username_count, "
                    "min(created_at) FILTER (WHERE username_key=%s) AS first_username "
                    "FROM account_auth_attempts WHERE environment=%s AND action=%s",
                    (address_key, address_key, username_key, username_key,
                     self.environment, action)).fetchone()
                # 任一维度超额都拒绝, 等待时间取所有超额窗口的最大剩余值。
                for count, first, limit in (("total", "first_total", policy.global_limit),
                                           ("address_count", "first_address", policy.ip_limit),
                                           ("username_count", "first_username", policy.username_limit)):
                    if row[count] >= limit:
                        retry_after = max(retry_after, max(1, math.ceil(
                            policy.window_seconds - (current - row[first]).total_seconds())))
                # 只有准入通过才记账; 事务结束后路由才进行密码验证。
                if not retry_after:
                    connection.execute(
                        "INSERT INTO account_auth_attempts "
                        "(environment, action, address_key, username_key, created_at) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (self.environment, action, address_key, username_key, current))
        except Exception as error:
            raise self.unavailable(action, error) from None
        # 事务正常完成后返回限流, 不把限流误判为数据库不可用。
        if retry_after:
            raise AccountGuardError("AUTH_RATE_LIMITED", 429, retry_after=retry_after)
