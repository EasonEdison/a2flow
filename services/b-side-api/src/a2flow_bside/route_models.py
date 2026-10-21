"""Validated HTTP request models, independent of service composition."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from skillweave_contracts.user_id import user_id_from_wire


# 限制条目 ID 和文本长度, 严格模式拒绝隐式类型转换及额外字段。
class MemoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    text: str = Field(min_length=1, max_length=1000)


# 记忆设置携带版本号, 单次更新条目数受限。
class MemorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)
    enabled: bool
    entries: list[MemoryEntry] = Field(max_length=20)


# 这里约束请求大小, 用户名格式和密码最小长度由账号路由继续校验。
class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


# 登录字段有长度上限, 防止未经认证的请求提交无限内容。
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


# 新会话标题可省略; 存储侧负责默认标题和用户绑定。
class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


# 客户端只选择动态 ID, 真实工作流结果由服务端按归属读取。
class RunReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    activityId: str = Field(min_length=1, max_length=256)


# 首次处理必须同时定位动态和具体异常, 不能只给一段无来源的说明。
class ProcessingTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    activityId: str = Field(min_length=1, max_length=256)
    attentionId: str = Field(min_length=1, max_length=256)


# 人工补充的处理总结限制长度, 不替代真实业务执行回执。
class ProcessingResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str = Field(min_length=1, max_length=2000)


# 普通消息携带稳定请求号, 网络重发应复用同一个号。
class MessageSend(BaseModel):
    conversationId: int = Field(gt=0)
    clientRequestId: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    text: str = Field(min_length=1, max_length=4000)
    runReferences: list[RunReference] = Field(default_factory=list, max_length=3)

    # 首次异常处理和继续已有任务互斥, 处理请求号单独用于任务轮次去重。
    processingTarget: ProcessingTarget | None = None
    processingTaskId: str | None = Field(default=None, min_length=1, max_length=128)
    processingRequestId: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]{1,128}$")

    # 处理目标与请求号必须成对出现, 避免任务绑定不完整。
    @model_validator(mode="after")
    def processing_target(self) -> Self:
        if self.processingTarget is not None and self.processingTaskId is not None:
            raise ValueError("PROCESSING_TARGET_CONFLICT")
        if bool(self.processingTarget or self.processingTaskId) != bool(self.processingRequestId):
            raise ValueError("PROCESSING_REQUEST_ID_REQUIRED")
        return self

    # 拒绝纯空白消息, 保留原文交给模型和持久化层。
    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("MESSAGE_TEXT_REQUIRED")
        return value


# 区分手动与对话启动; 业务入参可为结构化对象或待映射的文本。
class RunStart(BaseModel):
    sourceType: Literal["manual", "chat"] = "manual"
    workflowKey: str = Field(min_length=1, max_length=256)
    input: dict[str, object] | str


# 附加运行引用只传运行标识, 归属和实际结果由服务端检查。
class RunRefCreate(BaseModel):
    runId: str = Field(min_length=1, max_length=256)


# 内部启动协议禁止额外字段, 环境和请求号受固定格式约束。
class InternalRunStart(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requestId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    environment: str = Field(pattern=r"^(PRT|ONLINE)$")
    userId: int
    workflowKey: str = Field(min_length=1, max_length=256)
    input: dict[str, object] | str

    # 用户 ID 按共享线协议解析, 不依赖 Pydantic 的宽松数字转换。
    @field_validator("userId", mode="before")
    @classmethod
    def parse_user_id(cls, value: object) -> int:
        return user_id_from_wire(value)


# 旧交互入口明确携带节点和交互 ID, 提交内容只属于该节点。
class RunAction(BaseModel):
    nodeId: str = Field(min_length=1, max_length=256)
    interactionId: str = Field(min_length=1, max_length=256)
    actionName: str = Field(min_length=1, max_length=256)
    inputs: dict[str, object] = Field(default_factory=dict)


# 卡片动作必须包含请求号, 动作执行服务据此防止重复消费。
class ChatCardAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    requestId: str = Field(min_length=1, max_length=128)
    actionName: str = Field(min_length=1, max_length=128)
    inputs: dict[str, object]


# 工作流卡片在通用动作上补充所属节点和交互身份。
class WorkflowCardAction(ChatCardAction):
    nodeId: str = Field(min_length=1, max_length=256)
    interactionId: str = Field(min_length=1, max_length=256)


# 内部恢复同时定位续聊请求和原动作请求, 不能仅凭卡片任意推进。
class InternalResume(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    userId: int
    environment: Literal["PRT", "ONLINE"]
    requestId: str = Field(min_length=1, max_length=128)
    actionRequestId: str = Field(min_length=1, max_length=128)
    nodeId: str = Field(min_length=1, max_length=256)
    interactionId: str = Field(min_length=1, max_length=256)

    # 内部恢复的用户 ID 同样使用共享协议校验, 避免两条入口身份解释不同。
    @field_validator("userId", mode="before")
    @classmethod
    def parse_user_id(cls, value: object) -> int:
        return user_id_from_wire(value)


# 计划仅接受显式 cron 表达式, 语义验证由调度模块负责。
class CronRuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expression: str = Field(min_length=1, max_length=128)


# 计划保存工作流、时区和业务文本, 规则类型限定为 cron。
class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workflowKey: str = Field(min_length=1, max_length=256)
    ruleType: Literal["cron"]
    ruleJson: CronRuleInput
    timezone: str | None = Field(default=None, max_length=64)
    inputText: str = Field(min_length=1, max_length=4000)


# 更新字段可省略, 路由区分未提交字段与明确提交的值。
class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool | None = None
    ruleType: Literal["cron"] | None = None
    ruleJson: CronRuleInput | None = None
    timezone: str | None = Field(default=None, max_length=64)
    inputText: str | None = Field(default=None, min_length=1, max_length=4000)
