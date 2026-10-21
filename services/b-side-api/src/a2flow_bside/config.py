"""Explicit environment configuration; every value is required (fail-closed)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def _required(name: str) -> str:
    # 必填配置缺失直接阻止启动, 不隐式回退到其他数据库或环境。
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("MISSING_BSIDE_CONFIGURATION:" + name)
    return value


def browser_origin(value: str) -> str:
    """Exact browser origin for login and unsafe cookie-backed requests.

    Loopback is the safe private default; a public origin is an explicit
    operator decision (TLS should terminate in front). Path/query/userinfo
    are rejected. The exact-origin check still rejects cross-site calls.
    """
    if not isinstance(value, str):
        raise RuntimeError("INVALID_BSIDE_BROWSER_ORIGIN")
    # 结构化解析来源地址, 拒绝通配符、认证信息和非 Origin 路径。
    parts = urlsplit(value)
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or "*" in parts.netloc
            or parts.username is not None or parts.password is not None
            or parts.path not in {"", "/"} or parts.query or parts.fragment):
        raise RuntimeError("INVALID_BSIDE_BROWSER_ORIGIN")
    # 规范化只移除可选末尾斜线, 其他来源差异仍必须显式配置。
    origin = parts.scheme + "://" + parts.netloc
    if value not in {origin, origin + "/"}:
        raise RuntimeError("INVALID_BSIDE_BROWSER_ORIGIN")
    return origin


# 运行服务地址必须是合法 HTTP 来源, 防止把路径或凭据带入内部调用。
def runtime_url(value: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError("INVALID_BSIDE_RUNTIME_URL")
    parts = urlsplit(value)
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.path not in {"", "/"} or parts.query or parts.fragment):
        raise RuntimeError("INVALID_BSIDE_RUNTIME_URL")
    return parts.scheme + "://" + parts.netloc


def session_seconds(value: str) -> int:
    # 会话有效期限定为一分钟到七天, 错误文本不能转换为默认值。
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        raise RuntimeError("INVALID_BSIDE_SESSION_SECONDS") from None
    if not 60 <= seconds <= 7 * 24 * 3600:
        raise RuntimeError("INVALID_BSIDE_SESSION_SECONDS")
    return seconds


@dataclass(frozen=True)
# 冻结启动配置, 连接串和 pepper 不参与对象打印。
class BsideConfig:
    conninfo: str = field(repr=False)
    pepper: str = field(repr=False)
    browser_origin: str
    runtime_url: str
    environment: str
    namespace: str
    session_seconds: int
    browser_origins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # 所有可用站点都经过相同来源校验, 且必须包含主站点并统一协议。
        primary = browser_origin(self.browser_origin)
        origins = tuple(browser_origin(value) for value in (self.browser_origins or (primary,)))
        if primary not in origins or len({value.split(":", 1)[0] for value in origins}) != 1:
            raise RuntimeError("INVALID_BSIDE_BROWSER_ORIGINS")
        # 规范化结果写回冻结配置, 后续鉴权使用相同的精确来源列表。
        object.__setattr__(self, "browser_origin", primary)
        object.__setattr__(self, "browser_origins", origins)

    @classmethod
    def from_environment(cls) -> BsideConfig:
        # 读取显式存储与密钥配置, 短 pepper 不允许启动。
        conninfo = _required("A2FLOW_BSIDE_DATABASE_URL")
        pepper = _required("A2FLOW_BSIDE_PEPPER")
        if len(pepper) < 16:
            raise RuntimeError("INVALID_BSIDE_PEPPER")
        # 资源环境限制为 PRT 或 ONLINE, 资产命名空间同样必须明确。
        environment = _required("A2FLOW_BSIDE_ENVIRONMENT")
        if environment not in {"PRT", "ONLINE"}:
            raise RuntimeError("INVALID_BSIDE_ENVIRONMENT")
        namespace = _required("A2FLOW_BSIDE_ASSET_NAMESPACE")
        return cls(
            conninfo=conninfo,
            pepper=pepper,
            browser_origin=browser_origin(
                _required("A2FLOW_BSIDE_BROWSER_ORIGIN")),
            runtime_url=runtime_url(_required("A2FLOW_BSIDE_RUNTIME_URL")),
            environment=environment,
            namespace=namespace,
            session_seconds=session_seconds(
                _required("A2FLOW_BSIDE_SESSION_SECONDS")),
            # 多来源只在配置键存在时解析, 不能由请求动态扩展信任范围。
            browser_origins=tuple(value.strip() for value in
                _required("A2FLOW_BSIDE_BROWSER_ORIGINS").split(","))
                if "A2FLOW_BSIDE_BROWSER_ORIGINS" in os.environ else (),
        )
