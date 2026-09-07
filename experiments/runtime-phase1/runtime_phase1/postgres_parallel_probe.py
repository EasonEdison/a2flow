"""Two-process AsyncPostgresSaver proof for native parallel branch resume."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
import json
import logging
import operator
from pathlib import Path
from typing import Annotated, Any, Callable, TypedDict

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg import connect, sql
from psycopg.conninfo import make_conninfo


LOGGER = logging.getLogger(__name__)
PROBE_DATABASE = "runtime_probe"
PROBE_ROLE = "runtime_probe"
ConnectionFactory = Callable[..., Any]


class ProbeBootstrapError(RuntimeError):
    """Redacted bootstrap failure after the credential is invalidated."""


class DurableParallelState(TypedDict):
    """Append-only trace shared by the parent and native branch subgraphs."""

    trace: Annotated[list[str], operator.add]


@dataclass(frozen=True)
class ProcessEvidence:
    """Non-secret process evidence emitted for the bounded PG probe."""

    process: str
    thread_id: str
    before_trace: list[str]
    after_trace: list[str]
    interrupt_count: int
    joined: bool


def build_native_parallel_graph(checkpointer: AsyncPostgresSaver):
    """Compile native branch subgraphs without introducing a scheduler."""

    def wait_a(state: DurableParallelState) -> DurableParallelState:
        del state
        interrupt({"interactionId": "interaction-a", "nodeId": "A"})
        return {"trace": ["A_RESUMED"]}

    branch_a_builder = StateGraph(DurableParallelState)
    branch_a_builder.add_node("wait_a", wait_a)
    branch_a_builder.add_edge(START, "wait_a")
    branch_a_builder.add_edge("wait_a", END)
    branch_a = branch_a_builder.compile()

    def run_b1(state: DurableParallelState) -> DurableParallelState:
        del state
        return {"trace": ["B1"]}

    def run_b2(state: DurableParallelState) -> DurableParallelState:
        del state
        return {"trace": ["B2"]}

    branch_b_builder = StateGraph(DurableParallelState)
    branch_b_builder.add_node("run_b1", run_b1)
    branch_b_builder.add_node("run_b2", run_b2)
    branch_b_builder.add_edge(START, "run_b1")
    branch_b_builder.add_edge("run_b1", "run_b2")
    branch_b_builder.add_edge("run_b2", END)
    branch_b = branch_b_builder.compile()

    def join(state: DurableParallelState) -> DurableParallelState:
        del state
        return {"trace": ["JOIN"]}

    parent_builder = StateGraph(DurableParallelState)
    parent_builder.add_node("branch_a", branch_a)
    parent_builder.add_node("branch_b", branch_b)
    parent_builder.add_node("join", join)
    parent_builder.add_edge(START, "branch_a")
    parent_builder.add_edge(START, "branch_b")
    parent_builder.add_edge(["branch_a", "branch_b"], "join")
    parent_builder.add_edge("join", END)
    return parent_builder.compile(checkpointer=checkpointer)


def _read_password(password_file: Path) -> str:
    password = password_file.read_text(encoding="utf-8").strip()
    if not password:
        raise ValueError("probe password is empty")
    return password


def _connection_string(
    socket_directory: Path,
    password_file: Path,
    *,
    database: str = PROBE_DATABASE,
    user: str = PROBE_ROLE,
) -> str:
    """Build an in-memory libpq string without printing the password."""

    return make_conninfo(
        host=str(socket_directory),
        dbname=database,
        user=user,
        password=_read_password(password_file),
        connect_timeout=5,
    )


def _role_exists(cursor: Any) -> bool:
    cursor.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)",
        (PROBE_ROLE,),
    )
    return bool(cursor.fetchone()[0])


def _scram_verifier(connection: Any, probe_password: str) -> str:
    """Use libpq to derive a SCRAM verifier before composing fixed DDL."""

    encoding = connection.info.encoding
    encrypted = connection.pgconn.encrypt_password(
        probe_password.encode(encoding),
        PROBE_ROLE.encode(encoding),
        b"scram-sha-256",
    )
    verifier = encrypted.decode("ascii")
    if not verifier.startswith("SCRAM-SHA-256$"):
        raise ValueError("libpq did not return a SCRAM-SHA-256 verifier")
    return verifier


def _apply_probe_bootstrap(connection: Any, probe_password: str) -> None:
    """Keep the role NOLOGIN until fixed DDL and SCRAM setup both succeed."""

    with connection.cursor() as cursor:
        if _role_exists(cursor):
            cursor.execute(
                "ALTER ROLE runtime_probe NOLOGIN NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION CONNECTION LIMIT 2",
            )
        else:
            cursor.execute(
                "CREATE ROLE runtime_probe NOLOGIN NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOREPLICATION CONNECTION LIMIT 2",
            )
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = %s)",
            (PROBE_DATABASE,),
        )
        if not bool(cursor.fetchone()[0]):
            cursor.execute("CREATE DATABASE runtime_probe OWNER runtime_probe")

        verifier = _scram_verifier(connection, probe_password)
        cursor.execute(
            sql.SQL("ALTER ROLE runtime_probe PASSWORD {} LOGIN").format(
                sql.Literal(verifier)
            )
        )


def _disable_probe_role(
    admin_connection_string: str,
    probe_password_file: Path,
    connection_factory: ConnectionFactory,
) -> str:
    """Confirm NOLOGIN or return UNSAFE_UNKNOWN so the caller destroys PG."""

    try:
        with connection_factory(
            admin_connection_string,
            autocommit=True,
        ) as connection:
            with connection.cursor() as cursor:
                if not _role_exists(cursor):
                    credential_state = "ROLE_ABSENT"
                else:
                    cursor.execute("ALTER ROLE runtime_probe NOLOGIN")
                    credential_state = "ROLE_DISABLED"
    except Exception:
        credential_state = "UNSAFE_UNKNOWN"
    probe_password_file.unlink(missing_ok=True)
    return credential_state


def bootstrap_probe_database(
    socket_directory: Path,
    admin_password_file: Path,
    probe_password_file: Path,
    *,
    connection_factory: ConnectionFactory = connect,
) -> None:
    """Bootstrap through NOLOGIN and never send a plaintext password in DDL."""

    admin_connection_string = _connection_string(
        socket_directory,
        admin_password_file,
        database="runtime_admin",
        user="runtime_admin",
    )
    probe_password = _read_password(probe_password_file)
    try:
        with connection_factory(
            admin_connection_string,
            autocommit=True,
        ) as connection:
            _apply_probe_bootstrap(connection, probe_password)
    except Exception as error:
        credential_state = _disable_probe_role(
            admin_connection_string,
            probe_password_file,
            connection_factory,
        )
        LOGGER.error(
            "PG probe bootstrap failed; credentialState=%s errorType=%s",
            credential_state,
            type(error).__name__,
        )
        raise ProbeBootstrapError(
            "PG probe bootstrap failed; credentialState="
            f"{credential_state}; destroy isolated PostgreSQL before retry"
        ) from None


async def run_process_a(
    connection_string: str,
    thread_id: str,
) -> ProcessEvidence:
    """Create tables, run until the native A branch interrupts, then exit."""

    config = {"configurable": {"thread_id": thread_id}}
    async with AsyncPostgresSaver.from_conn_string(connection_string) as saver:
        await saver.setup()
        graph = build_native_parallel_graph(saver)
        state = await graph.ainvoke({"trace": []}, config)
    interrupts = state.get("__interrupt__", ())
    trace = list(state["trace"])
    if len(interrupts) != 1 or trace != ["B1", "B2"]:
        raise AssertionError(
            f"process A boundary mismatch: interrupts={len(interrupts)} trace={trace}"
        )
    return ProcessEvidence(
        process="A",
        thread_id=thread_id,
        before_trace=[],
        after_trace=trace,
        interrupt_count=len(interrupts),
        joined=False,
    )


async def run_process_b(
    connection_string: str,
    thread_id: str,
) -> ProcessEvidence:
    """Query process A's checkpoint and resume the interrupted native branch."""

    config = {"configurable": {"thread_id": thread_id}}
    async with AsyncPostgresSaver.from_conn_string(connection_string) as saver:
        graph = build_native_parallel_graph(saver)
        snapshot = await graph.aget_state(config)
        before_trace = list(snapshot.values.get("trace", ()))
        interrupts = [
            pending
            for task in snapshot.tasks
            for pending in task.interrupts
        ]
        if len(interrupts) != 1 or before_trace != ["B1", "B2"]:
            raise AssertionError(
                "process B did not observe process A's durable wait boundary"
            )
        state = await graph.ainvoke(Command(resume={"approved": True}), config)
    after_trace = list(state["trace"])
    completed_nodes = after_trace[:-1]
    if (
        after_trace[-1:] != ["JOIN"]
        or sorted(completed_nodes) != ["A_RESUMED", "B1", "B2"]
    ):
        raise AssertionError(f"process B resume mismatch: trace={after_trace}")
    return ProcessEvidence(
        process="B",
        thread_id=thread_id,
        before_trace=before_trace,
        after_trace=after_trace,
        interrupt_count=len(state.get("__interrupt__", ())),
        joined=True,
    )


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("process", choices=("A", "B"))
    parser.add_argument("--socket-directory", required=True, type=Path)
    parser.add_argument("--password-file", required=True, type=Path)
    parser.add_argument("--thread-id", required=True)
    args = parser.parse_args()
    connection_string = _connection_string(
        args.socket_directory,
        args.password_file,
    )
    runner = run_process_a if args.process == "A" else run_process_b
    evidence = await runner(connection_string, args.thread_id)
    print(json.dumps(asdict(evidence), sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
