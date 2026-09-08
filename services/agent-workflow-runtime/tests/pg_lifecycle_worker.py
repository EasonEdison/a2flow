"""AF04 opt-in OS-process fixture; only synthetic data, private credential files."""

from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import psycopg
from psycopg.rows import dict_row
from langchain_core.messages import AIMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from agent_workflow_runtime import ActionRejected, ActionService, LangGraphContinuation
from agent_workflow_runtime.lifecycle import RunLifecycle, RunStoppedControl
from agent_workflow_runtime.native_control import ControlledRunRunner, RunGraphBinding, guarded_node
from agent_workflow_runtime.postgres import PostgresInteractionRepository
from agent_workflow_runtime.postgres_lifecycle import PostgresRunRepository
from runtime_phase1.a2ui_probe import build_render_application_tool, validate_render_application_model_args
from runtime_phase1.engine_spine_probe import build_engine_spine_probe
from runtime_phase1.postgres_parallel_probe import _connection_string
from runtime_phase1.scripted_model import ScriptedToolModel
from runtime_phase1.skill_registry_adapter import SkillRegistryResolver
from runtime_phase1.use_skill_probe import build_use_skill_tool, validate_use_skill_model_args
from test_engine_spine_integration import IntegratedSkillMaterialPort
from support import Configuration, Resolver, context, interaction, request


OWNER = context().trusted_context
DEFINITION = "sample-workflow"
VERSIONS = (("WORKFLOW:sample", "v2"),)


def conninfo():
    return _connection_string(Path(os.environ["A2FLOW_RUNTIME04_SOCKET"]),
                              Path(os.environ["A2FLOW_RUNTIME04_PASSWORD_FILE"]))


@contextmanager
def connection():
    with psycopg.connect(conninfo(), autocommit=True, row_factory=dict_row,
                         connect_timeout=5, application_name="a2flow-runtime04-probe",
                         options="-c statement_timeout=10000 -c lock_timeout=5000") as conn:
        yield conn


def event(case, name, amount=1):
    with connection() as conn:
        conn.execute("""INSERT INTO runtime04_probe_events(case_id,name,value) VALUES(%s,%s,%s)
            ON CONFLICT(case_id,name) DO UPDATE SET value=runtime04_probe_events.value+EXCLUDED.value""",
                     (case, name, amount))


def value(case, name):
    with connection() as conn:
        row = conn.execute("SELECT value FROM runtime04_probe_events WHERE case_id=%s AND name=%s",
                           (case, name)).fetchone()
        return 0 if row is None else row["value"]


def wait_event(case, name):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if value(case, name):
            return
        time.sleep(.02)
    raise AssertionError("bounded AF04 barrier timeout")


class NoOldRunRepository(PostgresRunRepository):
    def __init__(self, forbidden=None):
        super().__init__(conninfo())
        self.forbidden = forbidden

    def get_run(self, owner, run_id, **kwargs):
        if run_id == self.forbidden:
            raise AssertionError("old full Run read")
        return super().get_run(owner, run_id, **kwargs)

    def operations(self, owner, run_id):
        if run_id == self.forbidden:
            raise AssertionError("old operation read")
        return super().operations(owner, run_id)

    def get_operation(self, owner, run_id, operation_id):
        if run_id == self.forbidden:
            raise AssertionError("old operation read")
        return super().get_operation(owner, run_id, operation_id)


class NoOldInteractions(PostgresInteractionRepository):
    def __init__(self, forbidden=None):
        super().__init__(conninfo())
        self.forbidden = forbidden

    def _check_old(self, run_id):
        if run_id == self.forbidden:
            raise AssertionError("old interaction/business result read")

    def get(self, key, owner=None):
        self._check_old(key[0])
        return super().get(key, owner)

    def for_run(self, owner, run_id):
        self._check_old(run_id)
        return super().for_run(owner, run_id)

    def for_node(self, owner, run_id, node_id):
        self._check_old(run_id)
        return super().for_node(owner, run_id, node_id)


class NoOldSaver(PostgresSaver):
    forbidden_thread = None

    def get_tuple(self, config):
        if config["configurable"]["thread_id"] == self.forbidden_thread:
            raise AssertionError("old checkpoint read")
        return super().get_tuple(config)

    def list(self, config, **kwargs):
        if config is None or config["configurable"].get("thread_id") == self.forbidden_thread:
            raise AssertionError("old or unscoped checkpoint list")
        return super().list(config, **kwargs)


def service_for(case, run, life, *, slow=False, forbidden=None):
    repo, config = NoOldInteractions(forbidden), Configuration()

    def executor(config, inputs, owner):
        # A third connection must see BOTH independent commits before dispatch.
        with connection() as conn:
            attempt = conn.execute("""SELECT count(*) AS n FROM runtime_controls
                WHERE user_id=%s AND environment=%s AND run_id=%s
                  AND document->>'status'='EXECUTING'""",
                (owner.user_id, owner.environment, run.run_id)).fetchone()["n"]
            operation = conn.execute("""SELECT count(*) AS n FROM runtime_operation_facts
                WHERE user_id=%s AND environment=%s AND run_id=%s
                  AND document->>'kind'='ACTION' AND document->>'status'='IN_FLIGHT'""",
                (owner.user_id, owner.environment, run.run_id)).fetchone()["n"]
        if attempt != 1 or operation != 1:
            raise AssertionError("both committed admissions must be independently visible")
        event(case, "commits_visible")
        event(case, "executor")
        if slow:
            event(case, "action_entered")
            wait_event(case, "action_release")
        return {"accepted": True, "actual": "late-or-current-action"}

    return repo, config, ActionService(repo, config, executor, None, lifecycle=life)


def graph_for(case, run, life, saver, service, config, *, resume=False):
    class Materials(IntegratedSkillMaterialPort):
        def load_skill(self, key, trusted):
            event(case, "skill")
            return super().load_skill(key, trusted)
    tools = [
        build_use_skill_tool(SkillRegistryResolver(Materials())),
        build_render_application_tool(Resolver(config), action_service=service),
    ]
    replies = [AIMessage(content="Actual verified completion.")]
    if not resume:
        replies = [
            AIMessage(content="", tool_calls=[{
                "name": "use_skill", "args": {"skillKey": "demo/evidence-first-brief"},
                "id": "af04-skill", "type": "tool_call",
            }]),
            AIMessage(content="", tool_calls=[{
                "name": "render_application",
                "args": {"applicationKey": "sample.interactive.route-selection", "data": {}},
                "id": "af04-render", "type": "tool_call",
            }]), *replies,
        ]
    graph = build_engine_spine_probe(
        ScriptedToolModel(responses=replies), tools,
        {"use_skill": validate_use_skill_model_args,
         "render_application": validate_render_application_model_args},
        ["use_skill", "render_application"], harness_profile_key="scriptedtoolmodel",
        checkpointer=saver, terminal_guard=service.assert_finalizable, run_lifecycle=life,
    )
    service.continuation = LangGraphContinuation(graph, lifecycle=life)
    return graph


def main(mode, case, options):
    forbidden = options.get("source") if mode == "restart" else None
    life = RunLifecycle(NoOldRunRepository(forbidden))
    runner = ControlledRunRunner(life, None, None)
    if mode == "restart":
        with NoOldSaver.from_conn_string(conninfo()) as saver:
            saver.forbidden_thread = options["old_thread"]
            def factory(run, lifecycle):
                event(case, "factory")
                if json.loads(run.initial_inputs_json) != {"fresh": options.get("input", "new")}:
                    raise AssertionError("fresh input mismatch")
                if run.versions != VERSIONS:
                    raise AssertionError("current configuration mismatch")
                _, config, service = service_for(case, run, lifecycle, forbidden=forbidden)
                return graph_for(case, run, lifecycle, saver, service, config), {
                    "messages": [{"role": "user", "content": "Fresh independent input."}],
                }
            runner = ControlledRunRunner(life, factory, lambda *_: VERSIONS)
            return runner.start(OWNER, "restart-" + case, DEFINITION,
                                {"fresh": options.get("input", "new")}, "node-test",
                                stopped_run_id=options["source"])
    if mode == "allocate":
        run, fresh = life.allocate(OWNER, "start-" + case, DEFINITION, {"old": "input"},
                                   "node-test", lambda *_: (("WORKFLOW:sample", "v1"),))
        return {"runId": run.run_id, "threadId": run.thread_id, "fresh": fresh}
    run_id = options["run_id"]
    if mode == "stop":
        owner = replace(OWNER, user_id="wrong-user") if options.get("wrong_owner") else OWNER
        if options.get("wrong_environment"):
            owner = replace(owner, environment="ONLINE")
        if options.get("race"):
            event(case, "stop_ready")
            wait_event(case, "race_release")
        return life.stop(owner, run_id, options.get("control", "stop-" + case))
    if mode == "corrupt_old":
        with connection() as conn:
            conn.execute("""UPDATE runtime_runs SET document=jsonb_set(
                jsonb_set(document,'{initial_inputs_json}','"forbidden prior input"'),
                '{versions}','"forbidden prior versions"')
                WHERE user_id=%s AND environment=%s AND run_id=%s AND document->>'status'='STOPPED'""",
                         (OWNER.user_id, OWNER.environment, run_id))
        return {"corrupted": True}
    if mode == "history_digest":
        digest = hashlib.sha256()
        with connection() as conn:
            for table in ("runtime_runs", "runtime_interactions", "runtime_operation_facts"):
                rows = conn.execute("SELECT document FROM " + table +
                    " WHERE user_id=%s AND environment=%s AND run_id=%s ORDER BY document::text",
                    (OWNER.user_id, OWNER.environment, run_id)).fetchall()
                digest.update(json.dumps(rows, sort_keys=True).encode())
        return {"digest": digest.hexdigest()}
    run = life.read(OWNER, run_id)
    if mode == "read":
        with life.repository.run_scope(OWNER, run_id):
            facts = life.repository.operations(OWNER, run_id)
        repo = PostgresInteractionRepository(conninfo())
        with repo.scope(OWNER, run_id):
            cards = repo.for_run(OWNER, run_id)
        return {"status": run.status, "threadId": run.thread_id,
                "cards": [{"interactionId": i.interaction_id, "phase": i.phase,
                           "attempts": [{"status": a.status, "businessSuccess": a.business_success,
                                         "resumeStatus": a.resume_status} for a in i.attempts]} for i in cards],
                "facts": [{"kind": f.kind, "status": f.status, "revision": f.admitted_revision,
                           "result": f.result_json} for f in facts]}
    if mode == "unknown":
        fact = life.admit(OWNER, run_id, run.entry_node_id, "ACTION")
        life.finish(OWNER, run_id, fact.operation_id, None, status="UNCONFIRMED")
        return {"saved": True}
    if mode == "success":
        event(case, "success_ready")
        wait_event(case, "race_release")
        life.succeed(OWNER, run_id)
        return {"succeeded": True}
    if mode == "node_race":
        event(case, "node_ready")
        wait_event(case, "race_release")
        builder = StateGraph(dict)
        def node(state):
            event(case, "node_executor")
            wait_event(case, "node_release")
            return {"actual": "node-result"}
        builder.add_node("entry", guarded_node(life, run.context(), node))
        builder.add_edge(START, "entry")
        builder.add_edge("entry", END)
        with PostgresSaver.from_conn_string(conninfo()) as saver:
            graph = RunGraphBinding(builder.compile(checkpointer=saver), life)
            return runner.invoke(run, graph, {})
    with NoOldSaver.from_conn_string(conninfo()) as saver:
        repo, config, service = service_for(case, run, life, slow=options.get("slow", False))
        graph = graph_for(case, run, life, saver, service, config, resume=mode != "graph_start")
        if mode == "graph_start":
            result = runner.invoke(run, graph, {"messages": [{"role": "user", "content": "Old run input."}]})
            return {"interrupts": len(result["__interrupt__"])}
        if mode == "native_resume":
            # Reject before even consulting the old native snapshot.
            saver.forbidden_thread = run.thread_id
            return runner.invoke(run, graph, Command(resume={"old": {"controlRequestId": "old"}}))
        if mode == "action":
            with repo.scope(OWNER, run_id):
                cards = repo.for_run(OWNER, run_id)
            if len(cards) != 1:
                raise AssertionError("expected one current-run card")
            result = runner.action(run, service, request(
                cards[0], actionName=options.get("action", "save_choice"),
                request_id=options.get("request_id", "request-1")))
            return result if isinstance(result, dict) else {
                "status": result.status, "resumeStatus": result.resume_status,
            }
    raise ValueError("unknown AF04 probe mode")


if __name__ == "__main__":
    try:
        result = main(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))
    except ActionRejected as error:
        result = {"rejected": error.code}
    except RunStoppedControl:
        # A test of the lifecycle primitive observed its private signal. This is
        # NOT the product runner's normalization to a STOPPED response.
        result = {"observedControlSignal": "RunStoppedControl"}
    except BaseException as error:
        result = {"probe_error": type(error).__name__}
    print(json.dumps(result, sort_keys=True))
