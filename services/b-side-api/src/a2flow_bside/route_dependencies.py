"""Typed callback contracts at the explicit HTTP composition boundary.

JSON objects remain open because remote asset/card schemas are extensible; the
service dependency itself is never an untyped container or global registry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

# 仅开放的资产和卡片 JSON 允许动态字段, 服务依赖本身保持具体类型。
JsonObject = dict[str, Any]


# 记忆条目具有稳定 ID, 内容仅作为用户偏好保存。
class MemoryEntryData(TypedDict):
    id: str
    text: str


# revision 用于并发更新检查, 条目列表与启用状态一起传递。
class MemoryState(TypedDict):
    revision: int
    enabled: bool
    entries: list[MemoryEntryData]


# 卡片动作将幂等请求号、动作名和提交字段作为一个固定协议。
class CardActionPayload(TypedDict):
    requestId: str
    actionName: str
    inputs: JsonObject


# 用有类型的回调声明装配边界, 不通过全局服务容器动态查找。
WorkflowCatalog = Callable[[int], list[JsonObject]]
MemoryView = Callable[[int], MemoryState]
MemoryReplace = Callable[[int, MemoryState], MemoryState]
# 卡片查询和动作都显式携带用户及会话, 不能仅凭卡片 ID 操作。
ChatCards = Callable[[int, str], list[JsonObject]]
ChatAction = Callable[[int, str, str, CardActionPayload], JsonObject]
