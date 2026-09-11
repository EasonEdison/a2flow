"""Opt-in independent-process PG probe. Credentials are read only from private files."""

from contextlib import contextmanager
from dataclasses import replace
import json
import operator
import os
from pathlib import Path
import sys
import time
from typing import Annotated

import psycopg
from langchain_core.messages import AIMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from psycopg.rows import dict_row

from agent_workflow_runtime import ActionRejected, ActionService, LangGraphContinuation
from agent_workflow_runtime.postgres import PostgresInteractionRepository
from agent_workflow_runtime.serialization import encode
from runtime_phase1.postgres_parallel_probe import _connection_string
from runtime_phase1.a2ui_probe import build_render_application_tool, validate_render_application_model_args
from runtime_phase1.engine_spine_probe import build_engine_spine_probe
from runtime_phase1.scripted_model import ScriptedToolModel
from runtime_phase1.skill_registry_adapter import SkillRegistryResolver
from runtime_phase1.use_skill_probe import build_use_skill_tool, validate_use_skill_model_args
from test_engine_spine_integration import IntegratedSkillMaterialPort
from support import Configuration, Resolver, context, interaction, request


def conninfo():
    return _connection_string(
        Path(os.environ["A2FLOW_RUNTIME03_SOCKET"]),
        Path(os.environ["A2FLOW_RUNTIME03_PASSWORD_FILE"]),
    )


@contextmanager
def connection():
    with psycopg.connect(conninfo(), autocommit=True, row_factory=dict_row,
                         application_name="a2flow-runtime03-probe",
                         options="-c statement_timeout=10000 -c lock_timeout=5000") as conn:
        yield conn


def event(run_id, name, value=1):
    with connection() as conn:
        conn.execute("""INSERT INTO runtime_probe_events (run_id, name, value)
            VALUES (%s,%s,%s) ON CONFLICT (run_id,name)
            DO UPDATE SET value=runtime_probe_events.value+EXCLUDED.value""",
                     (run_id, name, value))


def value(run_id, name):
    with connection() as conn:
        row = conn.execute("SELECT value FROM runtime_probe_events WHERE run_id=%s AND name=%s",
                           (run_id, name)).fetchone()
        return 0 if row is None else row["value"]


def wait_event(run_id, name):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if value(run_id, name):
            return
        time.sleep(.02)
    raise ActionRejected("PROBE_BARRIER_TIMEOUT")


def bound_item(config, run_id, card="first"):
    original = interaction(config, card)
    ctx = replace(context(), invocation_scope=replace(context().invocation_scope, run_id=run_id))
    return replace(original, context=ctx, graph_thread_id=run_id)


def service_for(run_id, mode="normal"):
    repo = PostgresInteractionRepository(conninfo())
    config = Configuration()

    def executor(config, inputs, owner):
        # This independent connection must observe the COMMITTED reservation.
        with connection() as conn:
            row = conn.execute("""SELECT count(*) AS count FROM runtime_controls
                WHERE user_id=%s AND environment=%s AND run_id=%s
                  AND document->>'status'='EXECUTING'""",
                               (owner.user_id, owner.environment, run_id)).fetchone()
            if row["count"] != 1:
                raise AssertionError("executor cannot see committed EXECUTING")
        event(run_id, "executor")
        if mode == "execution_loss":
            event(run_id, "lock_pid", repo._stack()[-1].connection.info.backend_pid)
            event(run_id, "entered")
            wait_event(run_id, "release")
        if mode == "executor_failure":
            raise RuntimeError("synthetic unavailable executor")
        return {"accepted": True}

    service = ActionService(repo, config, executor, None)

    def complete(item, rid):
        service.completion(item.key, {"controlRequestId": rid}, item.context.trusted_context)
    service.continuation = complete
    return repo, config, service


class ProbeState(MessagesState):
    trace: Annotated[list[str], operator.add]


def graph_for(saver, repo, config, service, run_id, *, resume=False, loss=False):
    class Materials(IntegratedSkillMaterialPort):
        def load_skill(self, key, trusted):
            event(run_id, "skill")
            return super().load_skill(key, trusted)

    tools = [
        build_use_skill_tool(SkillRegistryResolver(Materials())),
        build_render_application_tool(Resolver(config), action_service=service),
    ]
    responses = [AIMessage(content="Verified completion.")]
    if not resume:
        responses = [
            AIMessage(content="", tool_calls=[{
                "name": "use_skill", "args": {"skillKey": "demo/evidence-first-brief"},
                "id": "pg-skill", "type": "tool_call",
            }]),
            AIMessage(content="", tool_calls=[{
                "name": "render_application",
                "args": {"applicationKey": "sample.interactive.route-selection", "data": {}},
                "id": "pg-render", "type": "tool_call",
            }]),
            *responses,
        ]
    agent = build_engine_spine_probe(
        ScriptedToolModel(responses=responses), tools,
        {"use_skill": validate_use_skill_model_args,
         "render_application": validate_render_application_model_args},
        ["use_skill", "render_application"], harness_profile_key="scriptedtoolmodel",
        terminal_guard=service.assert_finalizable,
    )

    def finish_a(state):
        if loss:
            # This is INSIDE the real graph invocation, AFTER the completion Tool.
            # Killing the continuation session cannot retract this running graph.
            event(run_id, "graph_entered")
            wait_event(run_id, "release")
        event(run_id, "A")
        return {"trace": ["A"]}

    a = StateGraph(ProbeState)
    a.add_node("agent", agent)
    a.add_node("finish_a", finish_a)
    a.add_edge(START, "agent")
    a.add_edge("agent", "finish_a")
    a.add_edge("finish_a", END)
    b = StateGraph(ProbeState)
    for name in ("B1", "B2"):
        def step(state, name=name):
            event(run_id, name)
            return {"trace": [name]}
        b.add_node(name, step)
    b.add_edge(START, "B1")
    b.add_edge("B1", "B2")
    b.add_edge("B2", END)
    parent = StateGraph(ProbeState, context_schema=type(context()))
    parent.add_node("a", a.compile())
    parent.add_node("b", b.compile())
    parent.add_node("join", lambda state: {"trace": ["JOIN"]})
    parent.add_edge(START, "a")
    parent.add_edge(START, "b")
    parent.add_edge(["a", "b"], "join")
    parent.add_edge("join", END)
    graph = parent.compile(checkpointer=saver)
    native = LangGraphContinuation(graph)

    def continuation(item, rid):
        if loss:
            event(run_id, "lock_pid", repo._stack()[-1].connection.info.backend_pid)
        return native(item, rid)
    service.continuation = continuation
    return graph


def run(mode, run_id, options):
    repo, config, service = service_for(run_id, options.get("fault", "normal"))
    item = bound_item(config, run_id, options.get("card", "first"))
    owner = item.context.trusted_context
    if mode == "register":
        service.register(item)
        service.register(bound_item(config, run_id, "second"))
        return {"registered": True}
    if mode == "read":
        with repo.scope(owner, run_id):
            return {"items": [encode(item) for item in repo.for_run(owner, run_id)]}
    if mode == "submit":
        if options.get("stale"):
            index = options["stale"] - 1
            config.current = tuple((k, "changed" if i == index else v)
                                   for i, (k, v) in enumerate(config.current))
        if options.get("stopped"):
            with repo.scope(owner, run_id):
                repo.save(replace(repo.get(item.key, owner), run_active=False))
        if options.get("owner"):
            owner = replace(owner, user_id="other-user")
        if options.get("environment"):
            owner = replace(owner, environment="ONLINE")
        result = service.submit(request(
            item, options.get("request_id", "request-1"),
            actionName=options.get("action", "save_choice"),
            inputs={"selection": options.get("selection", "left")},
        ), owner)
        return {"status": result.status, "resume_status": result.resume_status}
    if mode.startswith("graph_"):
        # Official synchronous saver owns its autocommit/dict_row connection.
        with PostgresSaver.from_conn_string(conninfo()) as saver:
            graph = graph_for(saver, repo, config, service, run_id,
                              resume=mode != "graph_start", loss=mode == "graph_loss")
            graph_config = {"configurable": {"thread_id": run_id}}
            if mode == "graph_start":
                state = graph.invoke({"messages": [{"role": "user", "content": "Run probe"}],
                                      "trace": []}, graph_config, context=item.context)
                return {"trace": state["trace"], "interrupts": len(state["__interrupt__"])}
            if mode != "graph_read":
                with repo.scope(owner, run_id):
                    registered = [i for i in repo.for_run(owner, run_id)
                                  if i.interaction_id != "second"]
                if len(registered) != 1:
                    raise AssertionError("one native card required")
                service.submit(request(registered[0]), owner)
            snapshot = graph.get_state(graph_config)
            return {"trace": snapshot.values["trace"], "next": list(snapshot.next)}
    raise ValueError("unknown mode")


if __name__ == "__main__":
    try:
        result = run(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))
    except ActionRejected as error:
        result = {"rejected": error.code}
    except Exception as error:
        # No DSNs, credentials, SQL params or arbitrary exception text on stderr.
        result = {"probe_error": type(error).__name__}
    print(json.dumps(result, sort_keys=True))
