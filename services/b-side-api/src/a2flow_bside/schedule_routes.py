"""Schedule routes HTTP routes with explicit typed dependencies."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable

from croniter import CroniterBadDateError
from fastapi import APIRouter

from .errors import BsideError, RemoteRuntimeError
from .repositories import (
    SchedulesRepository,
)
from .route_dependencies import (
    JsonObject,
)
from .route_identity import CurrentIdentity
from .route_models import (
    ScheduleCreate,
    ScheduleUpdate,
)
from .route_support import _schedule_json
from .runtime_client import RuntimeClient
from .schedule_history import (
    ScheduleHistoryRepository,
    ScheduleRunView,
    ScheduleTrigger,
)
from .scheduling import ScheduleRuleError, next_run_after, parse_rule


def create_router(
    *,
    environment: str,
    schedules: SchedulesRepository,
    schedule_history: ScheduleHistoryRepository | None,
    runtime_client: RuntimeClient,
    clock: Callable[[], dt.datetime],
) -> APIRouter:
    # 定时接口只维护计划和读取历史, 实际触发由独立调度器负责。
    router = APIRouter()
    # 计划列表和历史共用一个状态读取通道, 避免页面占满 Runtime 读取容量。
    schedule_status_gate = asyncio.Semaphore(1)

    # 执行状态客户端绑定当前用户及固定部署环境。
    def _runtime(user_id: int) -> RuntimeClient:
        return runtime_client.for_user(user_id, environment)

    # 调度投递状态与运行生命周期分别返回, 消息已送达不等于工作流成功。
    async def trigger_view(trigger: ScheduleTrigger, user_id: int) -> ScheduleRunView:
        lifecycle = None
        if trigger.run_id:
            try:
                # Runtime admits bounded reads; list/history share one lane so
                # opening a schedule page does not consume its whole capacity.
                # 远端状态读取串行限流, 并在线程中执行同步 HTTP。
                async with schedule_status_gate:
                    actual = await asyncio.to_thread(_runtime(user_id).view, trigger.run_id)
                lifecycle = actual.get("lifecycle") or "UNKNOWN"
            # 运行状态查询失败明确显示 UNKNOWN, 不覆盖原触发记录。
            except RemoteRuntimeError:
                lifecycle = "UNKNOWN"
        # 保留计划、控制请求和真实运行三种身份, 方便页面跳转与追溯。
        return ScheduleRunView(
            scheduleId=trigger.schedule_id,
            controlId=trigger.control_id,
            runId=trigger.run_id,
            scheduledAt=trigger.scheduled_at,
            deliveryState=trigger.delivery_state,
            lifecycle=lifecycle,
            inputText=trigger.input_text,
        )

    # 用纯规则函数计算下次触发时间, 非法或没有未来触发点的规则拒绝保存。
    def _computed_next(rule_type: str, rule_json: JsonObject, timezone: str) -> dt.datetime:
        try:
            rule = parse_rule(rule_type, rule_json, timezone, clock())
            next_at = next_run_after(rule, clock())
        # 规则校验和日期计算错误统一映射为计划输入错误。
        except (ScheduleRuleError, CroniterBadDateError):
            raise BsideError("INVALID_SCHEDULE", 400) from None
        if next_at is None:
            raise BsideError("INVALID_SCHEDULE", 400)
        return next_at

    # 新建计划先检查支持范围, 再保存规则和计算出的未来触发点。
    @router.post("/api/schedules", response_model=None)
    async def create_schedule(*, body: ScheduleCreate, identity: CurrentIdentity) -> JsonObject:
        if body.workflowKey.startswith("personal-wf-"):
            raise BsideError("PERSONAL_WORKFLOW_SCHEDULING_UNSUPPORTED", 400)
        # 未指定时区沿用产品默认值, 规则计算仍使用明确的时区对象。
        timezone = body.timezone or "Asia/Shanghai"
        next_at = _computed_next(body.ruleType, body.ruleJson.model_dump(), timezone)
        # 计划归属和环境来自可信上下文, 客户端仅提供规则与业务需求。
        row = schedules.create(
            user_id=identity.userId,
            workflow_key=body.workflowKey,
            environment=environment,
            rule_type=body.ruleType,
            rule_json=body.ruleJson.model_dump(),
            timezone=timezone,
            input_text=body.inputText,
            next_run_at=next_at,
        )
        return _schedule_json(row)

    # 计划列表批量取得每个计划最近触发, 避免逐卡片查调度表。
    @router.get("/api/schedules", response_model=None)
    async def list_schedules(*, identity: CurrentIdentity) -> JsonObject:
        rows = [_schedule_json(row) for row in schedules.list_for(identity.userId)]
        if schedule_history is not None:
            triggers = await asyncio.to_thread(schedule_history.read, identity.userId, environment)
            # 只补充当前列表可见计划的运行状态, 不混入已删除或他人计划。
            visible = {str(row["id"]) for row in rows}
            latest_runs = await asyncio.gather(
                *(
                    trigger_view(trigger, identity.userId)
                    for trigger in triggers
                    if trigger.schedule_id in visible
                )
            )
            # 按计划 ID 回填最近运行, 计划自身的下次触发时间仍独立展示。
            by_schedule = {item.scheduleId: item for item in latest_runs}
            for row in rows:
                row["latestRun"] = by_schedule.get(str(row["id"]))
        return {"schedules": rows}

    # 单计划历史先检查用户和环境, 再按有时区时间游标分页。
    @router.get("/api/schedules/{schedule_id}/runs", response_model=None)
    async def schedule_runs(
        *,
        schedule_id: int,
        before: dt.datetime | None = None,
        identity: CurrentIdentity,
    ) -> JsonObject:
        row = schedules.get(schedule_id)
        if row is None or row["user_id"] != identity.userId or row["environment"] != environment:
            raise BsideError("NOT_FOUND", 404)
        if schedule_history is None:
            raise BsideError("SCHEDULE_HISTORY_UNAVAILABLE", 503)
        # 无时区游标拒绝使用, 避免服务器本地时区造成分页不稳定。
        if before is not None and before.utcoffset() is None:
            raise BsideError("INVALID_SCHEDULE_CURSOR", 400)
        # 多读一条用于判断下一页, 只对当前页的触发补充执行状态。
        triggers = await asyncio.to_thread(
            schedule_history.read,
            identity.userId,
            environment,
            schedule_id=schedule_id,
            before=before,
            limit=11,
        )
        return {
            "runs": await asyncio.gather(
                *(trigger_view(item, identity.userId) for item in triggers[:10])
            ),
            # 有更多记录时返回本页末条触发时间, 客户端据此读取更早记录。
            "nextCursor": triggers[9].scheduled_at if len(triggers) > 10 else None,
        }

    # 更新先校验归属及支持范围, 仅收集明确提交的字段。
    @router.patch("/api/schedules/{schedule_id}", response_model=None)
    async def update_schedule(
        *, schedule_id: int, body: ScheduleUpdate, identity: CurrentIdentity
    ) -> JsonObject:
        row = schedules.get(schedule_id)
        if row is None or row["user_id"] != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        if row["workflow_key"].startswith("personal-wf-"):
            raise BsideError("PERSONAL_WORKFLOW_SCHEDULING_UNSUPPORTED", 400)
        # 未提交字段保留原值, 输入文本和启用状态分别处理。
        fields: JsonObject = {}
        if body.enabled is not None:
            fields["enabled"] = body.enabled
        if body.inputText is not None:
            fields["input_text"] = body.inputText
        # 修改规则、时区或重新启用时才重算未来触发点。
        rule_changed = (
            body.ruleType is not None or body.ruleJson is not None or body.timezone is not None
        )
        reenabled = body.enabled is True and not row["enabled"]
        # 把新旧规则组合后整体校验, 不能保存半套无效调度配置。
        if rule_changed or reenabled:
            rule_type = body.ruleType or row["rule_type"]
            rule_json = (
                body.ruleJson.model_dump() if body.ruleJson is not None else row["rule_json"]
            )
            timezone = body.timezone or row["timezone"]
            fields["rule_type"] = rule_type
            fields["rule_json"] = rule_json
            fields["timezone"] = timezone
            fields["next_run_at"] = _computed_next(rule_type, rule_json, timezone)
        # 存储更新再次带用户条件, 防止路由读取之后发生越权覆盖。
        updated = schedules.update(schedule_id, identity.userId, **fields)
        if updated is None:
            raise BsideError("NOT_FOUND", 404)
        return _schedule_json(updated)

    # 删除仅作用于所属用户的计划, 不以全局计划 ID 直接删除。
    @router.delete("/api/schedules/{schedule_id}", response_model=None)
    async def delete_schedule(*, schedule_id: int, identity: CurrentIdentity) -> JsonObject:
        if not schedules.delete(schedule_id, identity.userId):
            raise BsideError("NOT_FOUND", 404)
        return {"ok": True}

    return router
