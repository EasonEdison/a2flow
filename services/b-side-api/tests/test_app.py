"""Offline ASGI tests for the b-side app (fakes; no database or Runtime)."""

import asyncio
import datetime as dt
import json
import re
import unittest

import httpx

from a2flow_bside.app import create_app
from a2flow_bside.errors import BsideError, RemoteRuntimeError

PEPPER = "test-pepper-0123456789abcdef"
ORIGIN = "http://127.0.0.1:14177"
NOW = dt.datetime(2026, 9, 19, 12, 0, 0, tzinfo=dt.timezone.utc)
ORIGIN_HEADERS = {"Origin": ORIGIN}


class FakeClock:
    def __init__(self):
        self.value = NOW

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value = self.value + dt.timedelta(seconds=seconds)


class FakeUsers:
    def __init__(self):
        self.rows = {}

    def create(self, *, username, password_hash, role="USER"):
        if any(row["username"] == username for row in self.rows.values()):
            raise BsideError("USERNAME_TAKEN", 409)
        user_id = len(self.rows) + 1
        self.rows[user_id] = {
            "user_id": user_id, "username": username,
            "password_hash": password_hash, "role": role}
        return user_id

    def find_by_username(self, username):
        for row in self.rows.values():
            if row["username"] == username:
                return dict(row)
        return None


class FakeSessions:
    def __init__(self, users=None):
        self.rows = {}
        self.users = users

    def create(self, *, token_sha256, user_id, expires_at):
        self.rows[token_sha256] = {"user_id": user_id, "expires_at": expires_at}

    def find_identity(self, token_sha256, now):
        row = self.rows.get(token_sha256)
        if row is None or row["expires_at"] <= now:
            return None
        record = self.users.rows[row["user_id"]]
        return {"userId": row["user_id"], "username": record["username"],
                "role": record["role"]}

    def delete(self, token_sha256):
        self.rows.pop(token_sha256, None)


class FakeConversations:
    def __init__(self):
        self.rows = {}
        self.next_id = 1

    def create(self, *, user_id, title):
        row = {"id": self.next_id, "user_id": user_id, "title": title,
               "created_at": NOW}
        self.next_id += 1
        self.rows[row["id"]] = row
        return {"id": row["id"], "title": row["title"],
                "created_at": row["created_at"]}

    def list_for(self, user_id, limit=50):
        return [{"id": r["id"], "title": r["title"],
                 "created_at": r["created_at"]}
                for r in self.rows.values() if r["user_id"] == user_id]

    def owner(self, conversation_id):
        row = self.rows.get(conversation_id)
        return row["user_id"] if row is not None else None


class FakeMessages:
    def __init__(self):
        self.rows = []
        self.next_id = 1

    def append(self, *, conversation_id, role, content, ref_kind=None,
               ref_id=None):
        row = {"id": self.next_id, "conversation_id": conversation_id,
               "role": role, "content": content, "ref_kind": ref_kind,
               "ref_id": ref_id, "created_at": NOW}
        self.next_id += 1
        self.rows.append(row)
        return dict(row)

    def list_for(self, conversation_id, limit=200):
        return [{"id": row["id"], "role": row["role"],
                 "content": row["content"], "ref_kind": row["ref_kind"],
                 "ref_id": row["ref_id"], "created_at": row["created_at"]}
                for row in self.rows
                if row["conversation_id"] == conversation_id][:limit]

    def update_delivery(self, *, conversation_id, message_id, content):
        for row in self.rows:
            if row['conversation_id'] == conversation_id and row['id'] == message_id:
                row['content'] = content
                return
        raise ValueError('CHAT_MESSAGE_MISSING')


class FakeSchedules:
    _PUBLIC = ("id", "workflow_key", "environment", "rule_type", "rule_json",
               "timezone", "input_text", "enabled", "next_run_at",
               "last_run_at", "created_at")

    def __init__(self):
        self.rows = {}
        self.next_id = 1

    def create(self, **fields):
        row = dict(fields)
        row["id"] = self.next_id
        self.next_id += 1
        row["enabled"] = True
        row["last_run_at"] = None
        row["created_at"] = NOW
        self.rows[row["id"]] = row
        return self._public(row)

    def list_for(self, user_id, limit=100):
        return [self._public(row) for row in self.rows.values()
                if row["user_id"] == user_id]

    def get(self, schedule_id):
        return self.rows.get(schedule_id)

    def update(self, schedule_id, user_id, **fields):
        row = self.rows.get(schedule_id)
        if row is None or row["user_id"] != user_id:
            return None
        row.update(fields)
        return self._public(row)

    def delete(self, schedule_id, user_id):
        row = self.rows.get(schedule_id)
        if row is None or row["user_id"] != user_id:
            return False
        del self.rows[schedule_id]
        return True

    def _public(self, row):
        return {key: row[key] for key in self._PUBLIC if key in row}


class FakeNotifications:
    def __init__(self):
        self.rows = {}
        self.next_id = 1

    def add(self, *, user_id, kind, title, body, read=False, ref_type=None,
            ref_id=None):
        self.rows[self.next_id] = {
            "id": self.next_id, "user_id": user_id, "kind": kind,
            "title": title, "body": body, "ref_type": ref_type,
            "ref_id": ref_id, "read": read, "created_at": NOW}
        self.next_id += 1

    def list_for(self, user_id, limit=50):
        rows = [row for row in self.rows.values()
                if row["user_id"] == user_id]
        rows.sort(key=lambda row: (row["read"], -row["id"]))
        return [{"id": row["id"], "kind": row["kind"], "title": row["title"],
                 "body": row["body"], "ref_type": row["ref_type"],
                 "ref_id": row["ref_id"], "read": row["read"],
                 "created_at": row["created_at"]} for row in rows][:limit]

    def mark_read(self, notification_id, user_id):
        row = self.rows.get(notification_id)
        if row is None or row["user_id"] != user_id:
            return False
        row["read"] = True
        return True


class FakeRunOwnership:
    def __init__(self):
        self.rows = {}

    def create(self, *, control_id, user_id, workflow_key):
        self.rows[control_id] = {
            "user_id": user_id, "workflow_key": workflow_key,
            "created_at": NOW}

    def bind_run_id(self, control_id, run_id):
        return None

    def list_for(self, user_id, limit=50):
        return [{"control_id": key, "workflow_key": row["workflow_key"],
                 "created_at": row["created_at"]}
                for key, row in self.rows.items()
                if row["user_id"] == user_id]

    def owned_by(self, user_id, control_id):
        row = self.rows.get(control_id)
        return row is not None and row["user_id"] == user_id

    def owner(self, control_id):
        row = self.rows.get(control_id)
        return row["user_id"] if row is not None else None


class FakeRuntimeClient:
    def __init__(self):
        self.calls = []
        self.controls = {}

    def for_user(self, user_id, environment):
        return self

    def start(self, control_request_id, definition_key, inputs):
        self.calls.append(("start", control_request_id, definition_key, inputs))
        self.controls[control_request_id] = {
            "controlRequestId": control_request_id,
            "runId": "run-" + control_request_id, "status": "RUNNING"}
        return dict(self.controls[control_request_id])

    def control(self, control_id):
        self.calls.append(("control", control_id))
        if control_id not in self.controls:
            raise RemoteRuntimeError("CONTROL_NOT_FOUND", 404)
        return dict(self.controls[control_id])

    def stop(self, run_id, control_request_id):
        self.calls.append(("stop", run_id, control_request_id))
        return {"controlRequestId": control_request_id,
                "status": "STOP_REQUESTED"}

    def action(self, run_id, node_id, payload):
        self.calls.append(("action", run_id, node_id, payload))
        return {"ok": True}

    def action_stream(self, run_id, node_id, payload):
        self.calls.append(("action", run_id, node_id, payload))
        yield "data: {\"type\": \"init\", \"runId\": \"" + run_id + "\"}\n\n"
        yield "data: {\"type\": \"surface\", \"view\": {\"runId\": \"" + run_id + "\", \"title\": \"活动策划\", \"lifecycle\": \"RUNNING\", \"nodes\": [], \"cards\": [], \"outputs\": [], \"availability\": \"AVAILABLE\"}}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    def surface_stream(self, run_id):
        yield "data: {\"type\": \"snapshot\", \"view\": {\"runId\": \"" + run_id + "\", \"title\": \"活动策划\", \"lifecycle\": \"RUNNING\", \"nodes\": [], \"cards\": [], \"outputs\": [], \"availability\": \"AVAILABLE\"}}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    def view(self, run_id):
        self.calls.append(("view", run_id))
        return {"runId": run_id, "title": "活动策划", "lifecycle": "RUNNING",
                "nodes": [], "cards": [], "outputs": [],
                "availability": "AVAILABLE"}


class FakeChatRunner:
    """Scripted runner; records calls and replays a fixed event sequence."""

    def __init__(self, events=None):
        self.events = list(events or [])
        self.calls = []

    async def iterate(self, *, user_id, conversation_id, text, turn_id):
        self.calls.append((user_id, conversation_id, text, turn_id))
        for event in self.events:
            yield event


def catalog(user_id):
    return [{"definitionKey": "activity-package-demo",
             "inputSchema": {"type": "object",
                             "required": ["requirement"],
                             "properties": {"requirement":
                                            {"type": "string"}}}}]


class Harness:
    def __init__(self, **overrides):
        self.clock = FakeClock()
        users = FakeUsers()
        self.components = {
            "users": users, "sessions": FakeSessions(users),
            "conversations": FakeConversations(),
            "messages": FakeMessages(), "schedules": FakeSchedules(),
            "notifications": FakeNotifications(),
            "run_ownership": FakeRunOwnership(),
            "runtime_client": FakeRuntimeClient(),
            "chat_runner": FakeChatRunner(),
            "workflow_catalog": catalog, "pepper": PEPPER,
            "browser_origin": ORIGIN, "environment": "PRT",
            "session_seconds": 7200, "now": self.clock,
        }
        self.components.update(overrides)
        self.app = create_app(**self.components)

    async def client(self):
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=self.app, raise_app_exceptions=False),
            base_url="http://127.0.0.1")


def _session_token(response):
    value = response.headers.get("set-cookie", "")
    match = re.search(r"a2flow_bside_session=([^;]+)", value)
    return match.group(1) if match else None


class AuthFlowTests(unittest.TestCase):
    async def _flow(self):
        harness = Harness()
        async with await harness.client() as client:
            register = await client.post(
                "/api/auth/register",
                json={"username": "alice-01", "password": "password-1"},
                headers=ORIGIN_HEADERS)
            self.assertEqual(200, register.status_code)
            token = _session_token(register)
            self.assertIsNotNone(token)
            session = await client.get("/api/auth/session")
            payload = session.json()
            self.assertEqual(200, session.status_code)
            self.assertTrue(re.fullmatch(r"[1-9][0-9]*", payload["userId"]), payload["userId"])
            self.assertEqual("alice-01", payload["username"])
            self.assertEqual("USER", payload["role"])
            duplicate = await client.post(
                "/api/auth/register",
                json={"username": "alice-01", "password": "password-2"},
                headers=ORIGIN_HEADERS)
            self.assertEqual(409, duplicate.status_code)
            self.assertEqual("USERNAME_TAKEN",
                             duplicate.json()["error"]["code"])
            short = await client.post(
                "/api/auth/register",
                json={"username": "bob-02", "password": "short"},
                headers=ORIGIN_HEADERS)
            self.assertEqual(400, short.status_code)
            self.assertEqual("INVALID_PASSWORD", short.json()["error"]["code"])
            bad = await client.post(
                "/api/auth/register",
                json={"username": "no space", "password": "password-3"},
                headers=ORIGIN_HEADERS)
            self.assertEqual(400, bad.status_code)
            self.assertEqual("INVALID_USERNAME", bad.json()["error"]["code"])

    def test_register_and_validation(self):
        asyncio.run(self._flow())

    async def _flow_login(self):
        harness = Harness()
        async with await harness.client() as client:
            await client.post("/api/auth/register",
                              json={"username": "carol-03",
                                    "password": "password-4"},
                              headers=ORIGIN_HEADERS)
            await client.post("/api/auth/logout", headers=ORIGIN_HEADERS)
            wrong = await client.post(
                "/api/auth/login",
                json={"username": "carol-03", "password": "not-the-pass"},
                headers=ORIGIN_HEADERS)
            self.assertEqual(401, wrong.status_code)
            self.assertEqual("INVALID_CREDENTIALS",
                             wrong.json()["error"]["code"])
            good = await client.post(
                "/api/auth/login",
                json={"username": "carol-03", "password": "password-4"},
                headers=ORIGIN_HEADERS)
            self.assertEqual(200, good.status_code)
            self.assertEqual("carol-03", good.json()["username"])
            await client.post("/api/auth/logout", headers=ORIGIN_HEADERS)
            after = await client.get("/api/auth/session")
            self.assertEqual(401, after.status_code)

    def test_login_logout(self):
        asyncio.run(self._flow_login())

    async def _flow_expiry(self):
        harness = Harness()
        async with await harness.client() as client:
            await client.post("/api/auth/register",
                              json={"username": "dave-04",
                                    "password": "password-5"},
                              headers=ORIGIN_HEADERS)
            harness.clock.advance(7201)
            expired = await client.get("/api/auth/session")
            self.assertEqual(401, expired.status_code)
            self.assertEqual("AUTHENTICATION_REQUIRED",
                             expired.json()["error"]["code"])

    def test_session_expiry(self):
        asyncio.run(self._flow_expiry())

    async def _flow_guards(self):
        harness = Harness()
        async with await harness.client() as client:
            no_origin = await client.post(
                "/api/auth/register",
                json={"username": "eve-05", "password": "password-6"})
            self.assertEqual(403, no_origin.status_code)
            self.assertEqual("ORIGIN_REQUIRED",
                             no_origin.json()["error"]["code"])
            wrong_origin = await client.post(
                "/api/auth/register",
                json={"username": "eve-05", "password": "password-6"},
                headers={"Origin": "http://evil.example"})
            self.assertEqual(403, wrong_origin.status_code)
            identity_header = await client.get(
                "/api/auth/session", headers={"x-user-id": "spoofed"})
            self.assertEqual(400, identity_header.status_code)
            self.assertEqual("IDENTITY_FIELDS_NOT_ALLOWED",
                             identity_header.json()["error"]["code"])
            query = await client.get("/api/auth/session?x=1")
            self.assertEqual(400, query.status_code)
            self.assertEqual("QUERY_PARAMETERS_NOT_ALLOWED",
                             query.json()["error"]["code"])
            unauth = await client.get("/api/auth/session")
            self.assertEqual(401, unauth.status_code)

    def test_request_guards(self):
        asyncio.run(self._flow_guards())


class OwnershipTests(unittest.TestCase):
    async def _register(self, client, username):
        response = await client.post(
            "/api/auth/register",
            json={"username": username, "password": "password-9"},
            headers=ORIGIN_HEADERS)
        return _session_token(response)

    async def _flow(self):
        harness = Harness()
        client_a = await harness.client()
        client_b = await harness.client()
        async with client_a, client_b:
            token_a = await self._register(client_a, "owner-a")
            token_b = await self._register(client_b, "owner-b")
            cookies_a = {"a2flow_bside_session": token_a}
            cookies_b = {"a2flow_bside_session": token_b}

            created = await client_a.post(
                "/api/conversations", json={"title": "mine"},
                headers=ORIGIN_HEADERS, cookies=cookies_a)
            self.assertEqual(200, created.status_code)
            conversation_id = created.json()["id"]
            cross = await client_b.get(
                f"/api/conversations/{conversation_id}/messages",
                cookies=cookies_b)
            self.assertEqual(404, cross.status_code)
            own = await client_a.get(
                f"/api/conversations/{conversation_id}/messages",
                cookies=cookies_a)
            self.assertEqual(200, own.status_code)
            self.assertEqual([], own.json()["messages"])

            schedule = await client_a.post(
                "/api/schedules",
                json={"workflowKey": "activity-package-demo",
                      "ruleType": "period",
                      "ruleJson": {"every": "1d"},
                      "inputText": "每天跑一次"},
                headers=ORIGIN_HEADERS, cookies=cookies_a)
            self.assertEqual(200, schedule.status_code)
            schedule_id = schedule.json()["id"]
            cross_list = await client_b.get("/api/schedules",
                                          cookies=cookies_b)
            self.assertEqual([], cross_list.json()["schedules"])
            cross_patch = await client_b.patch(
                f"/api/schedules/{schedule_id}", json={"enabled": False},
                headers=ORIGIN_HEADERS, cookies=cookies_b)
            self.assertEqual(404, cross_patch.status_code)
            own_list = await client_a.get("/api/schedules", cookies=cookies_a)
            self.assertEqual(1, len(own_list.json()["schedules"]))

            run = await client_a.post(
                "/api/runs",
                json={"workflowKey": "activity-package-demo",
                      "input": {"requirement": "需求"}},
                headers=ORIGIN_HEADERS, cookies=cookies_a)
            self.assertEqual(200, run.status_code)
            control_id = run.json()["controlRequestId"]
            cross_run = await client_b.get(f"/api/runs/{control_id}",
                                         cookies=cookies_b)
            self.assertEqual(404, cross_run.status_code)
            own_runs = await client_a.get("/api/runs", cookies=cookies_a)
            self.assertEqual(1, len(own_runs.json()["runs"]))

    def test_owner_isolation(self):
        asyncio.run(self._flow())


class ScheduleTests(unittest.TestCase):
    async def _flow(self):
        harness = Harness()
        async with await harness.client() as client:
            await client.post("/api/auth/register",
                              json={"username": "sched-01",
                                    "password": "password-8"},
                              headers=ORIGIN_HEADERS)
            created = await client.post(
                "/api/schedules",
                json={"workflowKey": "activity-package-demo",
                      "ruleType": "period", "ruleJson": {"every": "1d"},
                      "timezone": "Asia/Shanghai", "inputText": "周期"},
                headers=ORIGIN_HEADERS)
            self.assertEqual(200, created.status_code)
            body = created.json()
            self.assertTrue(body["enabled"])
            self.assertTrue(body["nextRunAt"] > NOW.isoformat())
            schedule_id = body["id"]
            past = await client.post(
                "/api/schedules",
                json={"workflowKey": "activity-package-demo",
                      "ruleType": "once",
                      "ruleJson": {"at": "2020-01-01T00:00:00+00:00"},
                      "inputText": "过去"},
                headers=ORIGIN_HEADERS)
            self.assertEqual(400, past.status_code)
            self.assertEqual("INVALID_SCHEDULE", past.json()["error"]["code"])
            bad_step = await client.post(
                "/api/schedules",
                json={"workflowKey": "activity-package-demo",
                      "ruleType": "period", "ruleJson": {"every": "2d"},
                      "inputText": "坏周期"},
                headers=ORIGIN_HEADERS)
            self.assertEqual(400, bad_step.status_code)
            disabled = await client.patch(
                f"/api/schedules/{schedule_id}", json={"enabled": False},
                headers=ORIGIN_HEADERS)
            self.assertEqual(False, disabled.json()["enabled"])
            hourly = await client.patch(
                f"/api/schedules/{schedule_id}",
                json={"ruleJson": {"every": "1h"}},
                headers=ORIGIN_HEADERS)
            next_at = hourly.json()["nextRunAt"]
            self.assertTrue(next_at <= (NOW + dt.timedelta(hours=1)).isoformat())
            deleted = await client.delete(
                f"/api/schedules/{schedule_id}", headers=ORIGIN_HEADERS)
            self.assertEqual(200, deleted.status_code)
            empty = await client.get("/api/schedules")
            self.assertEqual([], empty.json()["schedules"])

    def test_schedule_lifecycle(self):
        asyncio.run(self._flow())


class NotificationTests(unittest.TestCase):
    async def _flow(self):
        harness = Harness()
        async with await harness.client() as client:
            registered = await client.post(
                "/api/auth/register",
                json={"username": "note-01", "password": "password-7"},
                headers=ORIGIN_HEADERS)
            user_id = int(registered.json()["userId"])
            notes = harness.components["notifications"]
            notes.add(user_id=user_id, kind="waiting", title="待确认",
                      body="工作流 X 需要确认", ref_type="run", ref_id="c1")
            notes.add(user_id=user_id, kind="finished", title="完成",
                      body="工作流 Y 完成", read=True)
            notes.add(user_id=1002, kind="finished", title="他人",
                      body="不该可见")
            listed = await client.get("/api/notifications")
            rows = listed.json()["notifications"]
            self.assertEqual(2, len(rows))
            self.assertEqual("waiting", rows[0]["kind"])
            first_id = rows[0]["id"]
            marked = await client.post(
                f"/api/notifications/{first_id}/read",
                headers=ORIGIN_HEADERS)
            self.assertEqual(200, marked.status_code)
            reread = await client.get("/api/notifications")
            self.assertEqual(
                True, reread.json()["notifications"][0]["read"])
            missing = await client.post(
                "/api/notifications/99999/read", headers=ORIGIN_HEADERS)
            self.assertEqual(404, missing.status_code)

    def test_notification_flow(self):
        asyncio.run(self._flow())


class RunProxyTests(unittest.TestCase):
    async def _flow(self):
        harness = Harness()
        async with await harness.client() as client:
            await client.post(
                "/api/auth/register",
                json={"username": "run-01", "password": "password-6"},
                headers=ORIGIN_HEADERS)
            catalog_response = await client.get("/api/workflows")
            self.assertEqual(
                "activity-package-demo",
                catalog_response.json()["workflows"][0]["definitionKey"])
            started = await client.post(
                "/api/runs",
                json={"workflowKey": "activity-package-demo",
                      "input": {"requirement": "策划一次活动"}},
                headers=ORIGIN_HEADERS)
            self.assertEqual(200, started.status_code)
            self.assertEqual("SUBMITTED", started.json()["status"])
            control_id = started.json()["controlRequestId"]
            runtime = harness.components["runtime_client"]
            self.assertEqual(
                ("start", control_id, "activity-package-demo",
                 {"requirement": "策划一次活动"}), runtime.calls[0])
            detail = await client.get(f"/api/runs/{control_id}")
            self.assertEqual("run-" + control_id,
                             detail.json()["runId"])
            stopped = await client.post(
                f"/api/runs/{control_id}/stop", headers=ORIGIN_HEADERS)
            self.assertEqual(200, stopped.status_code)
            self.assertEqual(("stop", "run-" + control_id),
                             (runtime.calls[-1][0], runtime.calls[-1][1]))
            acted = await client.post(
                f"/api/runs/{control_id}/actions",
                json={"nodeId": "choose_plan", "interactionId": "i1",
                      "actionName": "select_activity_plan",
                      "inputs": {"optionId": "indoor"}},
                headers=ORIGIN_HEADERS)
            self.assertEqual(200, acted.status_code)
            last = runtime.calls[-1]
            self.assertEqual("action", last[0])
            self.assertEqual("run-" + control_id, last[1])
            self.assertEqual("choose_plan", last[2])
            self.assertEqual("select_activity_plan",
                             last[3]["actionName"])
            self.assertEqual({"optionId": "indoor"}, last[3]["inputs"])
            self.assertEqual("i1", last[3]["interactionId"])

    def test_run_proxy(self):
        asyncio.run(self._flow())


class ChatSseTests(unittest.TestCase):
    async def _flow(self):
        runner = FakeChatRunner([
            {"type": "text_delta", "text": "好的，",
             "modelMessageId": "model-final"},
            {"type": "text_delta", "text": "我帮你跑。",
             "modelMessageId": "model-final"},
            {"type": "workflow_confirm",
             "workflowKey": "activity-package-demo",
             "title": "活动策划"},
            {"type": "done", "content": "好的，我帮你跑。",
             "finalModelMessageId": "model-final"},
        ])
        harness = Harness(chat_runner=runner)
        async with await harness.client() as client:
            registered = await client.post(
                "/api/auth/register",
                json={"username": "chat-01", "password": "password-9"},
                headers=ORIGIN_HEADERS)
            user_id = int(registered.json()["userId"])
            created = await client.post(
                "/api/conversations", json={"title": "会话"},
                headers=ORIGIN_HEADERS)
            conversation_id = created.json()["id"]
            sent = await client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"text": "帮我策划一场活动"},
                headers=ORIGIN_HEADERS)
            self.assertEqual(200, sent.status_code)
            self.assertIn("text/event-stream", sent.headers["content-type"])
            body = sent.text
            lines = [line for line in body.split("\n") if line]
            events = [
                json.loads(line[len("data: "):])
                for line in lines if line.startswith("data: ")]
            self.assertEqual(
                ["turn_started", "text_delta", "text_delta", "workflow_confirm", "done"],
                [event["type"] for event in events])
            self.assertEqual(
                [(user_id, conversation_id, "帮我策划一场活动", "1")],
                [(call[0], call[1], call[2], call[3]) for call in runner.calls])
            history = await client.get(
                f"/api/conversations/{conversation_id}/messages")
            rows = history.json()["messages"]
            self.assertEqual(["user", "assistant"],
                             [row["role"] for row in rows])
            self.assertEqual("好的，我帮你跑。",
                             rows[1]["content"]["text"])
            self.assertEqual("completed", rows[1]["content"]["delivery"])
            self.assertTrue(all(event['messageId'] == str(rows[1]['id']) for event in events))
            self.assertEqual(
                "activity-package-demo",
                rows[1]["content"]["events"][0]["workflowKey"])
            empty = await client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"text": ""}, headers=ORIGIN_HEADERS)
            self.assertEqual(400, empty.status_code)
            self.assertEqual(str(user_id), registered.json()["userId"])

    def test_chat_sse_flow(self):
        asyncio.run(self._flow())

    async def _flow_guards(self):
        harness = Harness()
        async with await harness.client() as client:
            unauthorized = await client.post(
                "/api/conversations/1/messages",
                json={"text": "hi"}, headers=ORIGIN_HEADERS)
            self.assertEqual(401, unauthorized.status_code)
            await client.post(
                "/api/auth/register",
                json={"username": "chat-a", "password": "password-1"},
                headers=ORIGIN_HEADERS)
            other = await client.post(
                "/api/conversations", json={"title": "a"},
                headers=ORIGIN_HEADERS)
            conversation_id = other.json()["id"]
            await client.post("/api/auth/logout", headers=ORIGIN_HEADERS)
            await client.post(
                "/api/auth/register",
                json={"username": "chat-b", "password": "password-1"},
                headers=ORIGIN_HEADERS)
            cross = await client.post(
                f"/api/conversations/{conversation_id}/messages",
                json={"text": "hi"}, headers=ORIGIN_HEADERS)
            self.assertEqual(404, cross.status_code)

    def test_chat_sse_guards(self):
        asyncio.run(self._flow_guards())


if __name__ == "__main__":
    unittest.main()


class RunRefTests(unittest.TestCase):
    async def _flow(self):
        harness = Harness()
        async with await harness.client() as client:
            registered = await client.post(
                "/api/auth/register",
                json={"username": "runref-01", "password": "password-9"},
                headers=ORIGIN_HEADERS)
            self.assertEqual(200, registered.status_code)
            created = await client.post(
                "/api/conversations", json={"title": "会话"},
                headers=ORIGIN_HEADERS)
            conversation_id = created.json()["id"]
            started = await client.post(
                "/api/runs",
                json={"workflowKey": "activity-package-demo",
                      "input": {"requirement": "策划"}},
                headers=ORIGIN_HEADERS)
            self.assertEqual(200, started.status_code)
            control_id = started.json()["controlRequestId"]
            attached = await client.post(
                f"/api/conversations/{conversation_id}/run-refs",
                json={"runId": control_id}, headers=ORIGIN_HEADERS)
            self.assertEqual(200, attached.status_code)
            missing = await client.post(
                f"/api/conversations/{conversation_id}/run-refs",
                json={"runId": "not-owned"}, headers=ORIGIN_HEADERS)
            self.assertEqual(404, missing.status_code)
            history = await client.get(
                f"/api/conversations/{conversation_id}/messages")
            rows = history.json()["messages"]
            self.assertEqual(1, len(rows))
            self.assertEqual("run", rows[0]["refKind"])
            self.assertEqual(control_id, rows[0]["refId"])

    def test_run_refs(self):
        asyncio.run(self._flow())
