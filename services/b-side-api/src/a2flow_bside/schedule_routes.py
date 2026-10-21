"""Schedule routes HTTP routes with explicit typed dependencies."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable

from croniter import CroniterBadDateError
from fastapi import APIRouter, Depends

from .errors import BsideError, RemoteRuntimeError
from .identity import RequestIdentity
from .repositories import (
    SchedulesRepository,
)
from .route_dependencies import (
    JsonObject,
)
from .route_identity import identity
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
    router = APIRouter()
    schedule_status_gate = asyncio.Semaphore(1)

    def _runtime(user_id: int) -> RuntimeClient:
        return runtime_client.for_user(user_id, environment)

    async def trigger_view(trigger: ScheduleTrigger, user_id: int) -> ScheduleRunView:
        lifecycle = None
        if trigger.run_id:
            try:
                # Runtime admits bounded reads; list/history share one lane so
                # opening a schedule page does not consume its whole capacity.
                async with schedule_status_gate:
                    actual = await asyncio.to_thread(
                        _runtime(user_id).view, trigger.run_id
                    )
                lifecycle = actual.get("lifecycle") or "UNKNOWN"
            except RemoteRuntimeError:
                lifecycle = "UNKNOWN"
        return ScheduleRunView(
            scheduleId=trigger.schedule_id,
            controlId=trigger.control_id,
            runId=trigger.run_id,
            scheduledAt=trigger.scheduled_at,
            deliveryState=trigger.delivery_state,
            lifecycle=lifecycle,
            inputText=trigger.input_text,
        )

    def _computed_next(
        rule_type: str, rule_json: JsonObject, timezone: str
    ) -> dt.datetime:
        try:
            rule = parse_rule(rule_type, rule_json, timezone, clock())
            next_at = next_run_after(rule, clock())
        except (ScheduleRuleError, CroniterBadDateError):
            raise BsideError("INVALID_SCHEDULE", 400) from None
        if next_at is None:
            raise BsideError("INVALID_SCHEDULE", 400)
        return next_at

    @router.post("/api/schedules", response_model=None)
    async def create_schedule(
        body: ScheduleCreate, identity: RequestIdentity = Depends(identity)
    ) -> JsonObject:
        if body.workflowKey.startswith("personal-wf-"):
            raise BsideError("PERSONAL_WORKFLOW_SCHEDULING_UNSUPPORTED", 400)
        timezone = body.timezone or "Asia/Shanghai"
        next_at = _computed_next(body.ruleType, body.ruleJson.model_dump(), timezone)
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

    @router.get("/api/schedules", response_model=None)
    async def list_schedules(
        identity: RequestIdentity = Depends(identity),
    ) -> JsonObject:
        rows = [_schedule_json(row) for row in schedules.list_for(identity.userId)]
        if schedule_history is not None:
            triggers = await asyncio.to_thread(
                schedule_history.read, identity.userId, environment
            )
            visible = {str(row["id"]) for row in rows}
            latest_runs = await asyncio.gather(
                *(
                    trigger_view(trigger, identity.userId)
                    for trigger in triggers
                    if trigger.schedule_id in visible
                )
            )
            by_schedule = {item.scheduleId: item for item in latest_runs}
            for row in rows:
                row["latestRun"] = by_schedule.get(str(row["id"]))
        return {"schedules": rows}

    @router.get("/api/schedules/{schedule_id}/runs", response_model=None)
    async def schedule_runs(
        schedule_id: int,
        before: dt.datetime | None = None,
        identity: RequestIdentity = Depends(identity),
    ) -> JsonObject:
        row = schedules.get(schedule_id)
        if (
            row is None
            or row["user_id"] != identity.userId
            or row["environment"] != environment
        ):
            raise BsideError("NOT_FOUND", 404)
        if schedule_history is None:
            raise BsideError("SCHEDULE_HISTORY_UNAVAILABLE", 503)
        if before is not None and before.utcoffset() is None:
            raise BsideError("INVALID_SCHEDULE_CURSOR", 400)
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
            "nextCursor": triggers[9].scheduled_at if len(triggers) > 10 else None,
        }

    @router.patch("/api/schedules/{schedule_id}", response_model=None)
    async def update_schedule(
        schedule_id: int,
        body: ScheduleUpdate,
        identity: RequestIdentity = Depends(identity),
    ) -> JsonObject:
        row = schedules.get(schedule_id)
        if row is None or row["user_id"] != identity.userId:
            raise BsideError("NOT_FOUND", 404)
        if row["workflow_key"].startswith("personal-wf-"):
            raise BsideError("PERSONAL_WORKFLOW_SCHEDULING_UNSUPPORTED", 400)
        fields: JsonObject = {}
        if body.enabled is not None:
            fields["enabled"] = body.enabled
        if body.inputText is not None:
            fields["input_text"] = body.inputText
        rule_changed = (
            body.ruleType is not None
            or body.ruleJson is not None
            or body.timezone is not None
        )
        reenabled = body.enabled is True and not row["enabled"]
        if rule_changed or reenabled:
            rule_type = body.ruleType or row["rule_type"]
            rule_json = (
                body.ruleJson.model_dump()
                if body.ruleJson is not None
                else row["rule_json"]
            )
            timezone = body.timezone or row["timezone"]
            fields["rule_type"] = rule_type
            fields["rule_json"] = rule_json
            fields["timezone"] = timezone
            fields["next_run_at"] = _computed_next(rule_type, rule_json, timezone)
        updated = schedules.update(schedule_id, identity.userId, **fields)
        if updated is None:
            raise BsideError("NOT_FOUND", 404)
        return _schedule_json(updated)

    @router.delete("/api/schedules/{schedule_id}", response_model=None)
    async def delete_schedule(
        schedule_id: int, identity: RequestIdentity = Depends(identity)
    ) -> JsonObject:
        if not schedules.delete(schedule_id, identity.userId):
            raise BsideError("NOT_FOUND", 404)
        return {"ok": True}

    return router
