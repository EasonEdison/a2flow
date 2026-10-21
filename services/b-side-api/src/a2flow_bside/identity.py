"""Session identity resolution and fail-closed request guards for /api.

Client headers, bodies or query strings can never supply identity: the server
resolves the session cookie itself, exactly like the management preview host.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable
from skillweave_contracts.user_id import require_user_id

from . import auth
from .errors import BsideError

# 共享账号以此 Cookie 解析身份; 请求自带的用户头不能替代认证。
SESSION_COOKIE = "a2flow_bside_session"

# 列举禁止客户端伪造的身份头, 供统一入口拒绝。
_IDENTITY_HEADERS = frozenset({
    "x-a2flow-environment", "x-a2flow-role", "x-a2flow-roles",
    "x-a2flow-user-id", "x-environment", "x-role", "x-roles", "x-user-id",
})

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
# 冻结经过服务端解析的身份, 防止路由执行途中被修改。
class RequestIdentity:
    userId: int
    username: str
    role: str

    # 身份 ID 沿用共享协议校验, 不接受布尔值等伪整数。
    def __post_init__(self):
        require_user_id(self.userId)


def parse_session_token(cookie_value: str | None) -> str | None:
    # 先校验令牌格式, 再允许进入摘要计算和数据库查询。
    if not cookie_value:
        return None
    # new_session_token emits 32 random bytes as 43 URL-safe ASCII characters.
    # Validate before hash_session_token encodes ASCII in request middleware.
    if len(cookie_value) != 43 or not all(
            c.isascii() and (c.isalnum() or c in "-_") for c in cookie_value):
        return None
    return cookie_value


def require_origin(headers, browser_origin: str | tuple[str, ...]) -> None:
    # 写请求必须携带唯一且精确匹配的 Origin, 约束 Cookie 的跨站使用。
    origins = headers.getlist("origin")
    allowed = (browser_origin,) if isinstance(browser_origin, str) else browser_origin
    if len(origins) != 1 or origins[0] not in allowed:
        raise BsideError("ORIGIN_REQUIRED", 403)


def resolve_identity(cookie_value: str | None, *, sessions: object,
                     now: Callable[[], dt.datetime]) -> RequestIdentity | None:
    """Resolve the session cookie into an identity (may be None)."""
    # 只从服务端会话记录取得用户与角色, 不信任模型或浏览器指定身份。
    token = parse_session_token(cookie_value)
    if token is None:
        return None
    # 查询同时检查有效期; 不存在或过期的会话都不产生身份。
    value = sessions.find_identity(auth.hash_session_token(token), now())
    if value is None:
        return None
    return RequestIdentity(**value)
