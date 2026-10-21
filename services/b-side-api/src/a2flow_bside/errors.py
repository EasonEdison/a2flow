"""Stable failure codes and HTTP status mapping for the b-side service."""

from __future__ import annotations


# 产品可预期失败仅保存稳定错误码和 HTTP 状态, 避免响应暴露内部异常。
class BsideError(RuntimeError):
    """Intentional, stable, non-sensitive request failure."""

    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code = code
        self.status = status


# 远端执行错误单独建模, 调用方可区分通信失败与本地参数失败。
class RemoteRuntimeError(RuntimeError):
    """The Runtime control interface rejected or failed a proxied request."""

    def __init__(self, code: str, status: int = 502):
        super().__init__(code)
        self.code = code
        self.status = status
