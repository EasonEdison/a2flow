"""Disposable PostgreSQL failure-boundary probe; no model or business calls."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import psycopg
from psycopg.rows import dict_row
from a2flow_bside.durable_chat import DurableChat, DurableDispatcher
from a2flow_bside.repositories import MessagesRepository
from a2flow_bside.errors import BsideError


async def exercise(factory):
    checks = 0
    store = DurableChat(factory, environment="PRT")
    messages = MessagesRepository(factory)

    def conversation():
        with factory() as c:
            return c.execute(
                "INSERT INTO conversations(user_id) VALUES(1) RETURNING id"
            ).fetchone()["id"]

    def receive(cid, key="request"):
        return store.receive(
            user_id=1,
            conversation_id=cid,
            request_id=key,
            payload={"text": "hello"},
            references=[],
        )

    class Runner:
        def __init__(self):
            self.facts = {}
            self.calls = 0

        async def inspect_turn(self, **kw):
            return self.facts.get(kw["turn_id"], {"status": "NOT_STARTED"})

        async def iterate(self, **kw):
            self.calls += 1
            self.facts[kw["turn_id"]] = {"status": "BUSY"}
            await asyncio.sleep(0.05)
            events = [
                {"type": "text_delta", "text": "saved", "modelMessageId": "m"},
                {"type": "done", "content": "saved", "finalModelMessageId": "m"},
            ]
            self.facts[kw["turn_id"]] = {"status": "COMPLETED", "events": events}
            for event in events:
                yield event

    # Concurrent HTTP duplicates create exactly one atomic pair/intent.
    cid = conversation()
    with ThreadPoolExecutor(max_workers=8) as pool:
        turns = list(pool.map(lambda _: receive(cid), range(16)))
    assert len({t["input_message_id"] for t in turns}) == 1
    with factory() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM messages WHERE conversation_id=%s", (cid,)
            ).fetchone()["n"]
            == 2
        )
    try:
        store.receive(
            user_id=1,
            conversation_id=cid,
            request_id="request",
            payload={"text": "different"},
            references=[],
        )
    except BsideError as e:
        assert e.code == "CHAT_REQUEST_CONFLICT"
    else:
        raise AssertionError("payload conflict admitted")
    checks += 3
    ack_stream = store.stream(turns[0])
    ack = json.loads((await anext(ack_stream))[6:])
    assert ack["type"] == "turn_started" and ack["sequence"] == 1
    await ack_stream.aclose()
    checks += 1
    # Process restart after acceptance: replacement dispatcher discovers saved intent.
    runner = Runner()
    dispatch = DurableDispatcher(store, messages, runner)
    await asyncio.gather(
        dispatch.dispatch(turns[0]),
        DurableDispatcher(store, messages, runner).dispatch(turns[0]),
    )
    assert (
        runner.calls == 1
        and store.get(turns[0]["input_message_id"])["status"] == "COMPLETED"
    )
    checks += 1
    # Card completion rollback leaves no continuation; commit survives worker replacement.
    cid = conversation()
    completion = SimpleNamespace(
        owner=SimpleNamespace(user_id=1),
        conversation_id=str(cid),
        card_id="card:probe",
        request_id="submit",
        metadata={"definitionSource": "TEMPORARY"},
    )
    try:
        with factory() as c:
            store.observe_completion(c, completion)
            raise RuntimeError("simulated card transaction rollback")
    except RuntimeError:
        pass
    with factory() as c:
        assert (
            c.execute("SELECT count(*) AS n FROM chat_continuations").fetchone()["n"]
            == 0
        )
    with factory() as c:
        store.observe_completion(c, completion)
    store.materialize(messages, None)
    store.materialize(messages, None)
    pending = next(t for t in store.candidates() if t["conversation_id"] == cid)
    await DurableDispatcher(store, messages, runner).dispatch(pending)
    assert store.get(pending["input_message_id"])["status"] == "COMPLETED"
    with factory() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM messages WHERE conversation_id=%s", (cid,)
            ).fetchone()["n"]
            == 2
        )
    checks += 3
    # Runtime finished, projection commit fails: rebuild from immutable terminal events.
    cid = conversation()
    turn = receive(cid)

    class FailProjection(DurableChat):
        failed = False

        def save_projection(self, input_id, generation, **kw):
            if not self.failed and kw["content"]["delivery"] == "completed":
                self.failed = True
                raise RuntimeError("injected projection database failure")
            return super().save_projection(input_id, generation, **kw)

    before = runner.calls
    await DurableDispatcher(
        FailProjection(factory, environment="PRT"), messages, runner
    ).dispatch(turn)
    assert store.get(turn["input_message_id"])["status"] == "RUNNING"
    await DurableDispatcher(store, messages, runner).dispatch(turn)
    assert (
        runner.calls == before + 1
        and store.get(turn["input_message_id"])["status"] == "COMPLETED"
    )
    _, assistant = store.pair(turn)
    assert (
        assistant["content"]["text"] == "saved"
        and len(assistant["content"]["parts"]) == 1
    )
    events = [
        json.loads(line[6:])
        async for line in store.stream(turn)
        if line.startswith("data:")
    ]
    assert events[-1]["type"] == "done" and events[-1]["content"]["text"] == "saved"
    checks += 4
    # BUSY and ambiguous native execution never authorize another model/operation.
    cid = conversation()
    turn = receive(cid)
    before = runner.calls
    runner.facts[str(turn["input_message_id"])] = {"status": "BUSY"}
    await dispatch.dispatch(turn)
    assert (
        runner.calls == before
        and store.get(turn["input_message_id"])["status"] == "QUEUED"
    )
    runner.facts[str(turn["input_message_id"])] = {"status": "NEEDS_REVIEW"}
    await dispatch.dispatch(turn)
    assert (
        runner.calls == before
        and store.get(turn["input_message_id"])["status"] == "NEEDS_REVIEW"
    )
    _, assistant = store.pair(turn)
    assert assistant["content"]["delivery"] == "unconfirmed"
    checks += 3
    # A later queued turn cannot overtake an unresolved earlier execution.
    later = receive(cid, "later")
    assert later["input_message_id"] not in {
        t["input_message_id"] for t in store.candidates()
    }
    assert store.get(later["input_message_id"])["status"] == "NEEDS_REVIEW"
    _, blocked = store.pair(later)
    assert blocked["content"]["errorCode"] == "CHAT_PREVIOUS_TURN_REQUIRES_REVIEW"
    checks += 3
    # Processing receive atomically binds the same generic client request identity.
    from a2flow_bside.processing_tasks import ProcessingTasksRepository

    class Activities:
        def get(self, **kwargs):
            return {
                "runId": "run-probe",
                "attentionItems": [
                    {"attentionId": "attention-probe", "kind": "business"}
                ],
            }

    processing = ProcessingTasksRepository(factory, Activities())
    cid = conversation()

    def observer(c, context, user, assistant, *, new):
        if new:
            store.insert_turn(
                c,
                user_id=1,
                conversation_id=cid,
                request_id="processing:probe",
                digest="probe",
                input_message=user,
                assistant_message=assistant,
                processing_context=context,
            )
        store.record_request(
            c,
            user_id=1,
            conversation_id=cid,
            request_id="client-processing",
            payload={"text": "handle"},
            input_message=user,
            assistant_message=assistant,
        )

    kwargs = dict(
        user_id=1,
        environment="PRT",
        conversation_id=str(cid),
        request_id="probe",
        text="handle",
        references=[],
        target={"activityId": "activity-probe", "attentionId": "attention-probe"},
        turn_observer=observer,
    )
    first = processing.begin_turn(**kwargs)
    second = processing.begin_turn(**kwargs)
    assert first[0] and not second[0] and first[2]["id"] == second[2]["id"]
    accepted = store.request(
        user_id=1,
        conversation_id=cid,
        request_id="client-processing",
        payload={"text": "handle"},
    )
    user, _ = store.pair(accepted)
    assert (
        user["content"]["clientRequestId"] == "client-processing"
        and store.get(user["id"]) is not None
    )
    try:
        store.receive(
            user_id=1,
            conversation_id=cid,
            request_id="client-processing",
            payload={"text": "different normal send"},
            references=[],
        )
    except BsideError as error:
        assert error.code == "CHAT_REQUEST_CONFLICT"
    else:
        raise AssertionError("cross-kind client request conflict admitted")
    with factory() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM messages WHERE conversation_id=%s", (cid,)
            ).fetchone()["n"]
            == 2
        )
    checks += 4
    # One invalid continuation binding cannot starve other intents or ordinary turns.
    poison_cid = conversation()
    valid_cid = conversation()
    ordinary = receive(conversation())
    for case, conv in [("poison", poison_cid), ("valid", valid_cid)]:
        item = SimpleNamespace(
            owner=SimpleNamespace(user_id=1),
            conversation_id=str(conv),
            card_id="card:" + case,
            request_id="submit",
            metadata={"definitionSource": "TEMPORARY"},
        )
        with factory() as c:
            store.observe_completion(c, item)

    class BrokenBinding:
        def context_for_card(self, **kw):
            if kw["card_id"] == "card:poison":
                raise BsideError("PROCESSING_CARD_BINDING_UNCONFIRMED", 409)
            return None

    store.materialize(messages, BrokenBinding())
    with factory() as c:
        poison = c.execute(
            "SELECT recovery_status,materialized FROM chat_continuations WHERE conversation_id=%s",
            (poison_cid,),
        ).fetchone()
    assert poison["recovery_status"] == "NEEDS_REVIEW" and not poison["materialized"]
    valid = next(t for t in store.candidates() if t["conversation_id"] == valid_cid)
    await dispatch.dispatch(valid)
    await dispatch.dispatch(ordinary)
    assert store.get(valid["input_message_id"])["status"] == "COMPLETED"
    assert store.get(ordinary["input_message_id"])["status"] == "COMPLETED"
    checks += 3
    # A stale producer whose lock connection died cannot overwrite a newer repair.
    fenced = receive(conversation())
    generation1 = store.claim_generation(fenced["input_message_id"])
    generation2 = store.claim_generation(fenced["input_message_id"])
    store.set_status(fenced["input_message_id"], "RUNNING", generation2)
    kwargs = dict(
        conversation_id=fenced["conversation_id"],
        message_id=fenced["assistant_message_id"],
    )
    store.save_projection(
        fenced["input_message_id"],
        generation2,
        **kwargs,
        content={"text": "repaired", "delivery": "completed"},
    )
    store.set_status(fenced["input_message_id"], "COMPLETED", generation2)
    for action in [
        lambda: store.save_projection(
            fenced["input_message_id"],
            generation1,
            **kwargs,
            content={"text": "", "delivery": "unconfirmed"},
        ),
        lambda: store.event(
            fenced["input_message_id"],
            {"sequence": 2, "type": "text_delta", "text": "stale"},
            generation1,
        ),
    ]:
        try:
            action()
        except RuntimeError as error:
            assert str(error) == "CHAT_DISPATCH_FENCED"
        else:
            raise AssertionError("stale dispatch projection admitted")
    store.set_status(fenced["input_message_id"], "NEEDS_REVIEW", generation1)
    assert store.get(fenced["input_message_id"])["status"] == "COMPLETED"
    assert store.pair(fenced)[1]["content"]["text"] == "repaired"
    checks += 4
    # Real HTTP composition: request identity, new route, durable lifespan and replay.
    from test_app import Harness, ORIGIN_HEADERS
    from a2flow_bside.repositories import ConversationsRepository

    harness = Harness(
        conversations=ConversationsRepository(factory),
        messages=messages,
        durable_chat=store,
        chat_runner=runner,
    )
    async with harness.app.router.lifespan_context(harness.app):
        async with await harness.client() as client:
            registered = await client.post(
                "/api/auth/register",
                json={"username": "probe-user", "password": "probe-password"},
                headers=ORIGIN_HEADERS,
            )
            assert registered.status_code == 200
            created = await client.post(
                "/api/conversations", json={"title": "probe"}, headers=ORIGIN_HEADERS
            )
            cid = created.json()["id"]
            payload = {
                "conversationId": cid,
                "clientRequestId": "http-request",
                "text": "hello",
            }
            response = await asyncio.wait_for(
                client.post(
                    "/api/conversations/messages", json=payload, headers=ORIGIN_HEADERS
                ),
                5,
            )
            assert response.status_code == 200 and '"type": "done"' in response.text
            before = runner.calls
            repeat = await client.post(
                "/api/conversations/messages", json=payload, headers=ORIGIN_HEADERS
            )
            assert repeat.status_code == 200 and runner.calls == before
            conflict = await client.post(
                "/api/conversations/messages",
                json={**payload, "text": "changed"},
                headers=ORIGIN_HEADERS,
            )
            assert conflict.status_code == 409
            missing = await client.post(
                "/api/conversations/messages",
                json={"conversationId": cid, "text": "hello"},
                headers=ORIGIN_HEADERS,
            )
            assert missing.status_code == 400
            history = await client.get(
                "/api/conversations/messages", params={"conversationId": cid}
            )
            assert (
                history.status_code == 200
                and history.json()["messages"][0]["content"]["clientRequestId"]
                == "http-request"
            )
            assert (
                await client.get(f"/api/conversations/{cid}/messages")
            ).status_code == 404
            # Additional, undeclared query parameters cannot smuggle an identity.
            assert (
                await client.get(
                    "/api/conversations/messages",
                    params={"conversationId": cid, "userId": 2},
                )
            ).status_code == 400
            checks += 8
    return checks


def main():
    dsn = os.environ["A2FLOW_PROBE_DATABASE_URL"]
    if (
        psycopg.conninfo.conninfo_to_dict(dsn).get("dbname")
        != "a2flow_chat_reliability_probe_ci"
    ):
        raise RuntimeError("ISOLATED_PROBE_DATABASE_REQUIRED")
    schema = "chat_reliability_" + uuid.uuid4().hex

    def factory():
        return psycopg.connect(
            dsn, row_factory=dict_row, options="-c search_path=" + schema
        )

    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("CREATE SCHEMA " + schema)
    try:
        with factory() as c:
            c.execute(
                (
                    Path(__file__).resolve().parents[1] / "src/a2flow_bside/schema.sql"
                ).read_text()
            )
        checks = asyncio.run(exercise(factory))
    finally:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute("DROP SCHEMA " + schema + " CASCADE")
    print(
        json.dumps(
            {
                "result": "PASS",
                "probe": "chat-reliability",
                "checks": checks,
                "postgres": True,
                "probeResourcesRemoved": True,
            }
        )
    )


if __name__ == "__main__":
    main()
