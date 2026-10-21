"""Product turn inbox and dispatch. Never infer permission to replay from a lease."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from contextlib import contextmanager
from collections.abc import AsyncIterator, Iterator
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from agent_workflow_runtime.chat.cards import CardCompletion
from .chat_runner import ChatRunner, RuntimeTurnInspection
from .persistence_types import ConnectionFactory, DatabaseConnection, MessageRecord
from .processing_tasks import ProcessingContext, ProcessingTasksRepository
from .repositories import MessagesRepository

from .chat_delivery import ChatDelivery
from .errors import BsideError
from .interaction_continuation import continuation_reference

_LOG = logging.getLogger(__name__)


def encoded(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


class DurableChat:
    def __init__(self, factory: ConnectionFactory, *, environment: str) -> None:
        self.factory, self.environment = factory, environment

    def check_ready(self) -> None:
        with self.factory() as c:
            c.execute("SELECT input_message_id FROM chat_turns LIMIT 0")
            c.execute("SELECT reference FROM chat_continuations LIMIT 0")

    def request(self, *, user_id: int, conversation_id: int, request_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        digest = hashlib.sha256(encoded(payload).encode()).hexdigest()
        with self.factory() as c:
            row = c.execute(
                "SELECT r.*,COALESCE(t.status,'LEGACY') AS status FROM chat_requests r "
                "LEFT JOIN chat_turns t USING(input_message_id) WHERE r.user_id=%s AND r.environment=%s "
                "AND r.conversation_id=%s AND r.client_request_id=%s",
                (user_id, self.environment, conversation_id, request_id),
            ).fetchone()
            if row and row["request_digest"] != digest:
                raise BsideError("CHAT_REQUEST_CONFLICT", 409)
            return dict(row) if row else None

    def record_request(self, c: DatabaseConnection, *, user_id: int, conversation_id: int,
                       request_id: str, payload: dict[str, Any], input_message: MessageRecord,
                       assistant_message: MessageRecord) -> None:
        digest = hashlib.sha256(encoded(payload).encode()).hexdigest()
        c.execute(
            "INSERT INTO chat_requests(user_id,environment,conversation_id,client_request_id,"
            "request_digest,input_message_id,assistant_message_id) VALUES(%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (
                user_id,
                self.environment,
                int(conversation_id),
                request_id,
                digest,
                input_message["id"],
                assistant_message["id"],
            ),
        )
        row = c.execute(
            "SELECT request_digest,input_message_id FROM chat_requests WHERE user_id=%s AND environment=%s "
            "AND conversation_id=%s AND client_request_id=%s",
            (user_id, self.environment, int(conversation_id), request_id),
        ).fetchone()
        if (
            row["request_digest"] != digest
            or row["input_message_id"] != input_message["id"]
        ):
            raise BsideError("CHAT_REQUEST_CONFLICT", 409)
        c.execute(
            "UPDATE messages SET content=content || %s::jsonb WHERE id=%s",
            (encoded({"clientRequestId": request_id}), input_message["id"]),
        )

    def insert_turn(self, c: DatabaseConnection, *, user_id: int, conversation_id: int,
                    request_id: str, digest: str, input_message: MessageRecord,
                    assistant_message: MessageRecord, references: tuple[dict[str, Any], ...] = (),
                    processing_context: ProcessingContext | None = None) -> None:
        c.execute(
            "INSERT INTO chat_turns(user_id,environment,conversation_id,request_id,request_digest,"
            "input_message_id,assistant_message_id,run_references,processing_context) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) ON CONFLICT DO NOTHING",
            (
                user_id,
                self.environment,
                int(conversation_id),
                request_id,
                digest,
                input_message["id"],
                assistant_message["id"],
                encoded(list(references)),
                encoded(processing_context),
            ),
        )

    def receive(self, *, user_id: int, conversation_id: int, request_id: str, payload: dict[str, Any], references: list[dict[str, Any]]) -> dict[str, Any]:
        digest = hashlib.sha256(encoded(payload).encode()).hexdigest()
        with self.factory() as c:
            owner = c.execute(
                "SELECT user_id FROM conversations WHERE id=%s FOR UPDATE",
                (conversation_id,),
            ).fetchone()
            if owner is None or owner["user_id"] != user_id:
                raise BsideError("CONVERSATION_NOT_FOUND", 404)
            prior = c.execute(
                "SELECT * FROM chat_turns WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND request_id=%s",
                (user_id, self.environment, conversation_id, "message:" + request_id),
            ).fetchone()
            if prior:
                if prior["request_digest"] != digest:
                    raise BsideError("CHAT_REQUEST_CONFLICT", 409)
                return dict(prior)
            rows = []
            for role, content in [
                (
                    "user",
                    {
                        "text": payload["text"],
                        "delivery": "submitted",
                        "clientRequestId": request_id,
                        "runReferences": references,
                    },
                ),
                ("assistant", {"text": "", "delivery": "queued", "parts": []}),
            ]:
                rows.append(
                    dict(
                        c.execute(
                            "INSERT INTO messages(conversation_id,role,content) "
                            "VALUES (%s,%s,%s::jsonb) RETURNING *",
                            (conversation_id, role, encoded(content)),
                        ).fetchone()
                    )
                )
            self.insert_turn(
                c,
                user_id=user_id,
                conversation_id=conversation_id,
                request_id="message:" + request_id,
                digest=digest,
                input_message=rows[0],
                assistant_message=rows[1],
                references=references,
            )
            self.record_request(
                c,
                user_id=user_id,
                conversation_id=conversation_id,
                request_id=request_id,
                payload=payload,
                input_message=rows[0],
                assistant_message=rows[1],
            )
            return dict(
                c.execute(
                    "SELECT * FROM chat_turns WHERE input_message_id=%s",
                    (rows[0]["id"],),
                ).fetchone()
            )

    def observe_completion(self, connection: DatabaseConnection, completion: CardCompletion) -> None:
        metadata = completion.metadata
        # Workflow completions are owned by the Workflow outbox, never Chat.
        if metadata.get("workflow"):
            return
        write = "approval" in metadata or "completedApproval" in metadata
        if not write and metadata.get("definitionSource") != "TEMPORARY":
            return
        reference = continuation_reference(
            completion.card_id, completion.request_id if write else None
        )
        connection.execute(
            "INSERT INTO chat_continuations(user_id,environment,conversation_id,reference,"
            "card_id,request_id,write_completed) VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (
                completion.owner.user_id,
                self.environment,
                int(completion.conversation_id),
                reference,
                completion.card_id,
                completion.request_id,
                write,
            ),
        )

    def get(self, input_id: int) -> dict[str, Any] | None:
        with self.factory() as c:
            row = c.execute(
                "SELECT * FROM chat_turns WHERE input_message_id=%s", (input_id,)
            ).fetchone()
            return dict(row) if row else None

    def pair(self, turn: dict[str, Any]) -> tuple[MessageRecord, MessageRecord]:
        with self.factory() as c:
            rows = c.execute(
                "SELECT * FROM messages WHERE id IN (%s,%s) ORDER BY id",
                (turn["input_message_id"], turn["assistant_message_id"]),
            ).fetchall()
            return MessageRecord(**rows[0]), MessageRecord(**rows[1])

    def candidates(self) -> list[dict[str, Any]]:
        with self.factory() as c:
            blocked = c.execute(
                "UPDATE chat_turns t SET status='NEEDS_REVIEW',updated_at=now() "
                "WHERE t.environment=%s AND t.status='QUEUED' AND EXISTS(SELECT 1 FROM chat_turns p "
                "WHERE p.environment=t.environment AND p.conversation_id=t.conversation_id "
                "AND p.input_message_id<t.input_message_id AND p.status='NEEDS_REVIEW') "
                "RETURNING t.assistant_message_id",
                (self.environment,),
            ).fetchall()
            for row in blocked:
                c.execute(
                    "UPDATE messages SET content=content || %s::jsonb WHERE id=%s",
                    (
                        encoded(
                            {
                                "delivery": "unconfirmed",
                                "errorCode": "CHAT_PREVIOUS_TURN_REQUIRES_REVIEW",
                            }
                        ),
                        row["assistant_message_id"],
                    ),
                )
            return [
                dict(row)
                for row in c.execute(
                    "SELECT t.* FROM chat_turns t WHERE t.environment=%s "
                    "AND t.status IN ('QUEUED','RUNNING') AND t.next_attempt_at<=now() "
                    "AND NOT EXISTS(SELECT 1 FROM chat_turns p WHERE p.conversation_id=t.conversation_id "
                    "AND p.environment=t.environment AND p.input_message_id<t.input_message_id "
                    "AND p.status IN ('QUEUED','RUNNING','NEEDS_REVIEW')) ORDER BY t.input_message_id LIMIT 32",
                    (self.environment,),
                ).fetchall()
            ]

    @contextmanager
    def lock(self, conversation_id: int) -> Iterator[bool]:
        with self.factory() as c:
            c.autocommit = True
            key = "bside-chat:" + self.environment + ":" + str(conversation_id)
            acquired = c.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired",
                (key,),
            ).fetchone()["acquired"]
            try:
                yield acquired
            finally:
                if acquired:
                    c.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,)
                    )

    def claim_generation(self, input_id: int) -> int | None:
        with self.factory() as c:
            row = c.execute(
                "UPDATE chat_turns SET dispatch_generation=dispatch_generation+1 "
                "WHERE input_message_id=%s AND status IN ('QUEUED','RUNNING') RETURNING dispatch_generation",
                (input_id,),
            ).fetchone()
            return row["dispatch_generation"] if row else None

    def set_status(self, input_id: int, status: str, generation: int) -> None:
        with self.factory() as c:
            c.execute(
                "UPDATE chat_turns SET status=%s,next_attempt_at=now()+interval '2 seconds',updated_at=now() "
                "WHERE input_message_id=%s AND dispatch_generation=%s AND status IN ('QUEUED','RUNNING')",
                (status, input_id, generation),
            )

    def save_projection(self, input_id: int, generation: int, *, conversation_id: int,
                        message_id: int, content: dict[str, Any]) -> None:
        with self.factory() as c:
            row = c.execute(
                "SELECT assistant_message_id,conversation_id FROM chat_turns WHERE input_message_id=%s "
                "AND dispatch_generation=%s AND status IN ('QUEUED','RUNNING') FOR UPDATE",
                (input_id, generation),
            ).fetchone()
            if (
                row is None
                or row["assistant_message_id"] != message_id
                or row["conversation_id"] != conversation_id
            ):
                raise RuntimeError("CHAT_DISPATCH_FENCED")
            c.execute(
                "UPDATE messages SET content=%s::jsonb WHERE id=%s",
                (encoded(content), message_id),
            )

    def event(self, input_id: int, event: dict[str, Any], generation: int) -> None:
        with self.factory() as c:
            # Lock the generation row through journal commit, fencing a writer
            # whose advisory-lock connection disappeared while its producer lived.
            row = c.execute(
                "SELECT 1 FROM chat_turns WHERE input_message_id=%s AND dispatch_generation=%s "
                "AND status='RUNNING' FOR UPDATE",
                (input_id, generation),
            ).fetchone()
            if row is None:
                raise RuntimeError("CHAT_DISPATCH_FENCED")
            c.execute(
                "INSERT INTO chat_turn_events(input_message_id,sequence,event) VALUES (%s,%s,%s::jsonb) "
                "ON CONFLICT(input_message_id,sequence) DO UPDATE SET event=excluded.event",
                (input_id, event["sequence"], encoded(event)),
            )

    async def stream(self, turn: dict[str, Any]) -> AsyncIterator[str]:
        input_id = turn["input_message_id"]
        cursor = 1
        yield (
            "data: "
            + json.dumps(
                {
                    "type": "turn_started",
                    "sequence": 1,
                    "turnId": str(input_id),
                    "inputMessageId": str(input_id),
                    "messageId": str(turn["assistant_message_id"]),
                }
            )
            + "\n\n"
        )
        if turn.get("status") == "LEGACY":
            _, assistant = await asyncio.to_thread(self.pair, turn)
            completed = assistant["content"].get("delivery") in {
                "completed",
                "waiting_action",
            }
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "done" if completed else "error",
                        "sequence": 2,
                        "inputMessageId": str(input_id),
                        "messageId": str(turn["assistant_message_id"]),
                        "content": assistant["content"],
                        "code": None if completed else "CHAT_REQUIRES_REVIEW",
                    }
                )
                + "\n\n"
            )
            return
        while True:

            def read():
                with self.factory() as c:
                    events = c.execute(
                        "SELECT sequence,event FROM chat_turn_events WHERE input_message_id=%s "
                        "AND sequence>%s ORDER BY sequence",
                        (input_id, cursor),
                    ).fetchall()
                    current = c.execute(
                        "SELECT status FROM chat_turns WHERE input_message_id=%s",
                        (input_id,),
                    ).fetchone()
                    return events, current["status"]

            events, status = await asyncio.to_thread(read)
            for row in events:
                cursor = row["sequence"]
                yield "data: " + json.dumps(row["event"], ensure_ascii=False) + "\n\n"
                if row["event"].get("type") in {"done", "error"}:
                    return
            if status in {"COMPLETED", "NEEDS_REVIEW"}:
                # A crash can occur between final projection and event; return a factual snapshot.
                _, assistant = await asyncio.to_thread(self.pair, turn)
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "done" if status == "COMPLETED" else "error",
                            "sequence": cursor + 1,
                            "turnId": str(input_id),
                            "inputMessageId": str(input_id),
                            "messageId": str(turn["assistant_message_id"]),
                            "content": assistant["content"],
                            "code": None
                            if status == "COMPLETED"
                            else "CHAT_REQUIRES_REVIEW",
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                return
            yield ": pending\n\n"
            await asyncio.sleep(0.4)

    def materialize(self, messages: MessagesRepository, processing_tasks: ProcessingTasksRepository | None) -> None:
        with self.factory() as c:
            intents = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM chat_continuations WHERE environment=%s "
                    "AND materialized=false AND recovery_status='PENDING' AND next_attempt_at<=now() "
                    "ORDER BY created_at LIMIT 32",
                    (self.environment,),
                ).fetchall()
            ]
        for intent in intents:
            try:
                self._materialize_one(intent, messages, processing_tasks)
            except Exception as error:
                # Only local, idempotent preparation is retried. No model or business
                # dispatch happens here. A broken binding cannot starve other chats.
                self._materialization_failed(intent, error)

    def _materialization_failed(self, intent: dict[str, Any], error: Exception) -> None:
        review = isinstance(error, BsideError) and error.status < 500
        scope = (
            intent["user_id"],
            self.environment,
            intent["conversation_id"],
            intent["reference"],
        )
        with self.factory() as c:
            changed = c.execute(
                "UPDATE chat_continuations SET recovery_status=%s,error_code=%s,"
                "next_attempt_at=now()+interval '5 seconds' WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND reference=%s AND materialized=false RETURNING reference",
                (
                    "NEEDS_REVIEW" if review else "PENDING",
                    error.code
                    if isinstance(error, BsideError)
                    else "CHAT_CONTINUATION_PREPARATION_PENDING",
                    *scope,
                ),
            ).fetchone()
            if not changed or not review:
                return
            rows = c.execute(
                "SELECT * FROM messages WHERE conversation_id=%s AND ref_kind='temporary_interaction' "
                "AND ref_id=%s ORDER BY id",
                (intent["conversation_id"], intent["reference"]),
            ).fetchall()
            pair = {row["role"]: dict(row) for row in rows}
            if len(rows) == 2 and set(pair) == {"user", "assistant"}:
                self.insert_turn(
                    c,
                    user_id=intent["user_id"],
                    conversation_id=intent["conversation_id"],
                    request_id="card:" + intent["reference"],
                    digest=intent["reference"],
                    input_message=pair["user"],
                    assistant_message=pair["assistant"],
                )
                c.execute(
                    "UPDATE chat_turns SET status='NEEDS_REVIEW',updated_at=now() WHERE input_message_id=%s",
                    (pair["user"]["id"],),
                )
                c.execute(
                    "UPDATE messages SET content=content || %s::jsonb WHERE id=%s",
                    (
                        encoded({"delivery": "unconfirmed", "errorCode": error.code}),
                        pair["assistant"]["id"],
                    ),
                )

    def _materialize_one(self, intent: dict[str, Any], messages: MessagesRepository, processing_tasks: ProcessingTasksRepository | None) -> None:
        # Each step is idempotent. Intent remains durable until binding and dispatch are saved.
        _, user, assistant = messages.claim_interaction_continuation(
            user_id=intent["user_id"],
            conversation_id=intent["conversation_id"],
            card_id=intent["card_id"],
            request_id=intent["request_id"],
            write_completed=intent["write_completed"],
        )
        context = None
        if processing_tasks is not None:
            context = processing_tasks.context_for_card(
                user_id=intent["user_id"],
                environment=self.environment,
                conversation_id=str(intent["conversation_id"]),
                card_id=intent["card_id"],
            )
            if context:
                context = processing_tasks.bind_continuation(
                    user_id=intent["user_id"],
                    environment=self.environment,
                    conversation_id=str(intent["conversation_id"]),
                    task_id=context["taskId"],
                    card_id=intent["card_id"],
                    input_message_id=user["id"],
                    assistant_message_id=assistant["id"],
                    confirmation_request_id=intent["request_id"]
                    if intent["write_completed"]
                    else None,
                )
        with self.factory() as c:
            self.insert_turn(
                c,
                user_id=intent["user_id"],
                conversation_id=intent["conversation_id"],
                request_id="card:" + intent["reference"],
                digest=intent["reference"],
                input_message=user,
                assistant_message=assistant,
                processing_context=context,
            )
            c.execute(
                "UPDATE chat_continuations SET materialized=true WHERE user_id=%s AND environment=%s "
                "AND conversation_id=%s AND reference=%s",
                (
                    intent["user_id"],
                    self.environment,
                    intent["conversation_id"],
                    intent["reference"],
                ),
            )


class _Replay:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self.events = events

    async def iterate(self, *, user_id: int, conversation_id: int, text: str, turn_id: str,
                      run_references: tuple[dict[str, Any], ...] = (),
                      processing_context: ProcessingContext | None = None) -> AsyncIterator[dict[str, Any]]:
        for event in self.events:
            yield event


class _FencedProjection:
    def __init__(self, store: DurableChat, input_id: int, generation: int) -> None:
        self.store, self.input_id, self.generation = store, input_id, generation

    def update_delivery(self, *, conversation_id: int, message_id: int, content: dict[str, Any]) -> None:
        self.store.save_projection(self.input_id, self.generation, conversation_id=conversation_id, message_id=message_id, content=content)


class DurableDispatcher:
    def __init__(self, store: DurableChat, messages: MessagesRepository, runner: ChatRunner,
                 processing_tasks: ProcessingTasksRepository | None = None) -> None:
        self.store, self.messages, self.runner, self.processing_tasks = (
            store,
            messages,
            runner,
            processing_tasks,
        )
        self.active: set[int] = set()

    async def dispatch(self, turn: dict[str, Any]) -> None:
        # Dedicated session lock survives transaction commits; Runtime independently
        # arbitrates actual execution. Lock loss never authorizes business replay.
        with self.store.lock(turn["conversation_id"]) as acquired:
            if not acquired:
                return
            current = await asyncio.to_thread(self.store.get, turn["input_message_id"])
            if current["status"] not in {"QUEUED", "RUNNING"}:
                return
            generation = await asyncio.to_thread(
                self.store.claim_generation, turn["input_message_id"]
            )
            if generation is None:
                return
            projection = _FencedProjection(
                self.store, turn["input_message_id"], generation
            )
            facts = await self.runner.inspect_turn(
                user_id=turn["user_id"],
                conversation_id=turn["conversation_id"],
                turn_id=str(turn["input_message_id"]),
            )
            state = facts["status"]
            if state == "BUSY":
                await asyncio.to_thread(
                    self.store.set_status,
                    turn["input_message_id"],
                    current["status"],
                    generation,
                )
                return
            user, assistant = await asyncio.to_thread(self.store.pair, turn)
            if state == "NEEDS_REVIEW":
                content = {
                    **assistant["content"],
                    "delivery": "unconfirmed",
                    "errorCode": "CHAT_REQUIRES_REVIEW",
                }
                await asyncio.to_thread(
                    projection.update_delivery,
                    conversation_id=turn["conversation_id"],
                    message_id=assistant["id"],
                    content=content,
                )
                await asyncio.to_thread(
                    self.store.set_status,
                    turn["input_message_id"],
                    "NEEDS_REVIEW",
                    generation,
                )
                return
            if state not in {"NOT_STARTED", "COMPLETED"}:
                raise ValueError("INVALID_RUNTIME_TURN_STATUS")
            await asyncio.to_thread(
                self.store.set_status, turn["input_message_id"], "RUNNING", generation
            )
            delivery = ChatDelivery(
                messages=projection,
                runner=_Replay(facts["events"])
                if state == "COMPLETED"
                else self.runner,
                user_id=turn["user_id"],
                conversation_id=turn["conversation_id"],
                text=user["content"]["text"],
                input_message=user,
                assistant_message=assistant,
                run_references=turn["run_references"],
                processing_context=turn["processing_context"],
            )
            delivery.detach()

            async def emit(event: dict[str, Any]) -> None:
                delivery.sequence += 1
                # Errors remain recoverable through inspect; no premature terminal event.
                if event["type"] in {"error", "done", "turn_started"}:
                    return
                await asyncio.to_thread(
                    self.store.event,
                    user["id"],
                    {
                        **event,
                        "sequence": delivery.sequence,
                        "messageId": str(assistant["id"]),
                        "inputMessageId": str(user["id"]),
                    },
                    generation,
                )

            delivery.emit = emit
            await delivery.produce()
            if delivery.content["delivery"] in {"completed", "waiting_action"}:
                await asyncio.to_thread(
                    self.store.set_status, user["id"], "COMPLETED", generation
                )
            # Failure deliberately remains RUNNING. The next inspection determines
            # completed projection repair versus NEEDS_REVIEW; never blind retry.

    async def run(self, stop: asyncio.Event) -> None:
        async def guarded(turn: dict[str, Any]) -> None:
            try:
                await self.dispatch(turn)
            except Exception:
                _LOG.exception("Chat durable dispatch inspection failed")
            finally:
                self.active.discard(turn["input_message_id"])

        tasks: set[asyncio.Task[None]] = set()
        try:
            while not stop.is_set():
                try:
                    await asyncio.to_thread(
                        self.store.materialize, self.messages, self.processing_tasks
                    )
                except Exception:
                    _LOG.exception("Chat continuation inbox scan failed")
                try:
                    for turn in await asyncio.to_thread(self.store.candidates):
                        if len(tasks) >= 8:
                            break
                        if turn["input_message_id"] in self.active:
                            continue
                        self.active.add(turn["input_message_id"])
                        task = asyncio.create_task(guarded(turn))
                        tasks.add(task)
                        task.add_done_callback(tasks.discard)
                except Exception:
                    _LOG.exception("Chat durable inbox scan failed")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
        finally:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
