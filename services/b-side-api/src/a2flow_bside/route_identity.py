"""Resolve the identity already authenticated by the app middleware."""

from typing import Annotated

from fastapi import Depends, Request

from .errors import BsideError
from .identity import RequestIdentity


def identity(request: Request) -> RequestIdentity:
    # 只接受中间件保存的已认证身份对象, 缺失时直接返回未登录。
    value = request.scope.get("a2flow.bside.identity")
    if not isinstance(value, RequestIdentity):
        raise BsideError("AUTHENTICATION_REQUIRED", 401)
    return value


# 路由通过 FastAPI 依赖复用认证结果, 后续仍要检查资源归属。
CurrentIdentity = Annotated[RequestIdentity, Depends(identity)]
