"""Minimal self-hosted account auth: scrypt password hashing + session tokens.

Stdlib only (no new runtime dependency). The hash format embeds its parameters
so a future migration to argon2/bcrypt can be introduced without resetting
users. All comparisons are constant-time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# 固定派生参数供写入与验证共用; 随机盐使相同密码生成不同摘要。
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16
_SESSION_BYTES = 32


def hash_password(password: str, *, pepper: str) -> str:
    # 拒绝空密码; 这里生成不可逆摘要, 不保存可读取的明文。
    if not isinstance(password, str) or not password:
        raise ValueError("EMPTY_PASSWORD")
    # 每次生成独立随机盐, pepper 从受保护配置注入。
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8") + pepper.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    # 将算法标识、盐和派生结果编码为可存储的字符串。
    return (
        "scrypt$"
        + base64.b64encode(salt).decode("ascii")
        + "$"
        + base64.b64encode(digest).decode("ascii")
    )


def verify_password(password: str, encoded: str, *, pepper: str) -> bool:
    # 验证入口先检查类型, 坏数据直接视为密码不匹配。
    if not isinstance(password, str) or not isinstance(encoded, str):
        return False
    try:
        # 只解析支持的算法和合法 Base64, 避免坏记录触发昂贵计算。
        scheme, salt_text, digest_text = encoded.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_text.encode("ascii"), validate=True)
        expected = base64.b64decode(digest_text.encode("ascii"), validate=True)
        # 检查盐及摘要长度后, 使用与写入相同的参数重新派生。
        if len(salt) != _SALT_BYTES or len(expected) != _SCRYPT_DKLEN:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8") + pepper.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            dklen=_SCRYPT_DKLEN,
        )
        # 恒定时间比较摘要; 格式错误统一返回验证失败。
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# 会话凭据使用密码学随机数, 明文仅交给浏览器 Cookie。
def new_session_token() -> str:
    return secrets.token_urlsafe(_SESSION_BYTES)


# 数据库查询使用令牌摘要, 不把原始会话凭据写入会话表。
def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()
