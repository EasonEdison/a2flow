"""Loopback gRPC ingress; Java alone authenticates browser/admin identity."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

import grpc
from a2flow.management.v1 import management_agent_pb2 as pb
from a2flow.management.v1 import management_agent_pb2_grpc as rpc

from .bridge import local_target
from .models import AgentError, AgentIdentity, encode, identifier
from .runner import ManagementRunner
from .store import ManagementStore

LOGGER = logging.getLogger(__name__)
Response = TypeVar("Response")


def identity(context: pb.AgentContext, *, require_grant: bool = True) -> AgentIdentity:
    if require_grant and not context.grant:
        raise AgentError("MANAGEMENT_GRANT_REQUIRED")
    return AgentIdentity(context.user_id, context.namespace, context.environment, context.grant)


def limit(value: int) -> int:
    if value == 0:
        return 50
    if not 1 <= value <= 100:
        raise AgentError("INVALID_PAGE_LIMIT")
    return value


def conversation(row: dict[str, Any]) -> pb.Conversation:
    return pb.Conversation(
        id=row["id"], title=row["title"], created_at=row["created_at"], updated_at=row["updated_at"]
    )


def turn(row: dict[str, Any]) -> pb.AgentTurn:
    return pb.AgentTurn(
        **{
            key: row[key]
            for key in ["turn_id", "request_id", "status", "message", "final_text", "error_code"]
        }
    )


class ManagementAgentService(rpc.ManagementAgentServicer):
    def __init__(self, store: ManagementStore, runner: ManagementRunner) -> None:
        self.store, self.runner = store, runner
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="management-agent")
        self.capacity = threading.BoundedSemaphore(1)

    @staticmethod
    def guarded(response: Callable[..., Response], operation: Callable[[], Response]) -> Response:
        try:
            return operation()
        except AgentError as exc:
            return response(error_code=exc.code)
        except (ValueError, TypeError):
            return response(error_code="INVALID_MANAGEMENT_REQUEST")
        except Exception as exc:
            LOGGER.warning(
                "management_request_failed response=%s code=%s exception=%s",
                getattr(response, "__name__", "response"),
                "MANAGEMENT_SERVICE_UNAVAILABLE",
                type(exc).__name__,
            )
            return response(error_code="MANAGEMENT_SERVICE_UNAVAILABLE")

    def CreateConversation(
        self, request: pb.CreateConversationRequest, context: grpc.ServicerContext
    ) -> pb.CreateConversationResponse:
        del context
        return self.guarded(
            pb.CreateConversationResponse,
            lambda: pb.CreateConversationResponse(
                conversation=conversation(
                    self.store.create(
                        identity(request.context, require_grant=False),
                        request.request_id,
                        request.title,
                    )
                )
            ),
        )

    def ListConversations(
        self, request: pb.ListConversationsRequest, context: grpc.ServicerContext
    ) -> pb.ListConversationsResponse:
        del context

        def run() -> pb.ListConversationsResponse:
            rows, token = self.store.list_conversations(
                identity(request.context, require_grant=False),
                request.page_token,
                limit(request.limit),
            )
            return pb.ListConversationsResponse(
                items=[conversation(row) for row in rows], next_page_token=token
            )

        return self.guarded(pb.ListConversationsResponse, run)

    def ReadConversation(
        self, request: pb.ReadConversationRequest, context: grpc.ServicerContext
    ) -> pb.ReadConversationResponse:
        del context

        def run() -> pb.ReadConversationResponse:
            if request.after_event_seq < 0:
                raise AgentError("INVALID_EVENT_CURSOR")
            result = self.store.read(
                identity(request.context),
                request.conversation_id,
                request.after_event_seq,
                limit(request.limit),
            )
            return pb.ReadConversationResponse(
                conversation=conversation(result["conversation"]),
                turns=[turn(row) for row in result["turns"]],
                events=[
                    pb.AgentEvent(
                        sequence=x["sequence"],
                        turn_id=x["turn_id"],
                        type=x["type"],
                        payload_json=encode(x["payload_json"]),
                    )
                    for x in result["events"]
                ],
                next_event_seq=result["next_event_seq"],
                has_more=result["has_more"],
                can_send=result["can_send"],
                mutations_blocked=result["mutations_blocked"],
            )

        return self.guarded(pb.ReadConversationResponse, run)

    def SendMessage(
        self, request: pb.SendMessageRequest, context: grpc.ServicerContext
    ) -> pb.SendMessageResponse:
        del context

        def run() -> pb.SendMessageResponse:
            who = identity(request.context)
            cid = identifier(request.conversation_id)
            identifier(request.request_id)
            row = self.store.existing(who, cid, request.request_id, request.message)
            if row is None:
                if not self.capacity.acquire(blocking=False):
                    raise AgentError("MANAGEMENT_AGENT_BUSY")
                released = False
                try:
                    row, created = self.store.claim(who, cid, request.request_id, request.message)
                    if created:

                        def worker() -> None:
                            try:
                                self.runner.run(who, cid, row)
                            finally:
                                self.capacity.release()

                        try:
                            self.executor.submit(worker)
                        except RuntimeError:
                            self.store.finish(
                                who,
                                cid,
                                row["turn_id"],
                                "FAILED",
                                error="MANAGEMENT_WORKER_UNAVAILABLE",
                            )
                            raise AgentError("MANAGEMENT_WORKER_UNAVAILABLE") from None
                    else:
                        self.capacity.release()
                    released = True
                finally:
                    if not released:
                        self.capacity.release()
            return pb.SendMessageResponse(
                conversation_id=cid,
                turn_id=row["turn_id"],
                request_id=row["request_id"],
                status=row["status"],
            )

        return self.guarded(pb.SendMessageResponse, run)


def serve(target: str, store: ManagementStore, runner: ManagementRunner) -> None:
    service = ManagementAgentService(store, runner)
    server = grpc.server(
        ThreadPoolExecutor(max_workers=4),
        options=[
            ("grpc.max_receive_message_length", 2 * 1024 * 1024),
            ("grpc.max_send_message_length", 16 * 1024 * 1024),
        ],
    )
    rpc.add_ManagementAgentServicer_to_server(service, server)
    if server.add_insecure_port(local_target(target)) == 0:
        raise AgentError("MANAGEMENT_PORT_UNAVAILABLE")
    with store.host_lock():
        store.recover_crashed()
        server.start()
        try:
            server.wait_for_termination()
        except KeyboardInterrupt:
            server.stop(5).wait()
        finally:
            service.executor.shutdown(wait=True)
