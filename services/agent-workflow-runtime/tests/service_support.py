"""Synthetic in-memory assembly; never a production database fallback."""

from collections import Counter
from contextlib import contextmanager

from agent_workflow_runtime.models import ActionRejected
from agent_workflow_runtime.native_control import ControlledRunRunner
from agent_workflow_runtime.projections import receipt, snapshot
from agent_workflow_runtime.service import ExecutionSession, RuntimeService

from test_controlled_interaction import ControlledInteractionTest


class MemoryProjection:
    def __init__(self, runs, interactions):
        self.runs, self.interactions = runs, interactions

    def control(self, owner, control_id):
        with self.runs.lock:
            raw = self.runs.controls.get((owner, control_id))
            return receipt(raw, control_id)

    def restart_identity(self, owner, run_id):
        with self.runs.lock:
            raw = self.runs.restart_identity(owner, run_id)
            if raw is None:
                raise ActionRejected("RUN_NOT_FOUND")
            if raw["status"] != "STOPPED":
                raise ActionRejected("RESTART_SOURCE_OUTSIDE_THIS_SLICE")
            return raw

    def run(self, owner, run_id):
        with self.runs.lock:
            raw = self.runs.runs.get((owner, run_id))
            if raw is None:
                raise ActionRejected("RUN_NOT_FOUND")
            run = {"run_id": run_id, "status": raw["status"], "revision": raw["revision"]}
            run["initial_control_id"] = raw["initial_control_id"]
            run["initial_control_status"] = self.runs.controls[(owner, raw["initial_control_id"])]["status"]
            counts = Counter(
                (f["node_id"], f["kind"], f["status"])
                for (who, rid, _), f in self.runs.facts.items() if who == owner and rid == run_id
            )
        operations = [{"node_id": n, "kind": k, "status": s, "count": count}
                      for (n, k, s), count in sorted(counts.items())]
        # Saved test records are immutable; don't take the long Action scope lock.
        rows = []
        for item in tuple(self.interactions.items.values()):
            if item.context.trusted_context != owner or item.key[0] != run_id:
                continue
            row = {"node_id": item.key[1], "interaction_id": item.key[2], "phase": item.phase,
                   "run_active": item.run_active, "node_waiting": item.node_waiting,
                   "attempt_count": len(item.attempts)}
            if item.attempts:
                a = item.attempts[-1]
                row.update(control_id=a.request.control_request_id, attempt_status=a.status,
                           business_success=a.business_success, interaction_completed=a.interaction_completed,
                           resume_status=a.resume_status)
            rows.append(row)
        value = snapshot(run, operations, sorted(rows, key=lambda row: (row["node_id"], row["interaction_id"])))
        value["consistency"] = "NON_ATOMIC_TEST_OBSERVATION"
        return value


class ServiceFixture:
    def __init__(self):
        self.engine = ControlledInteractionTest()
        self.engine.setUp()
        self.owner = self.engine.run.owner
        self.life, self.runs, self.repo = self.engine.life, self.engine.runs, self.engine.repo
        self.entry_calls = 0
        self.factory_calls = 0
        self.factory_hook = None
        self.projection = MemoryProjection(self.runs, self.repo)
        self.runner = ControlledRunRunner(self.life, self.graph_factory, lambda *_: self.engine.config.current)
        self.service = RuntimeService(self.life, self.projection, self.session, self.entry)

    def entry(self, owner, definition):
        self.entry_calls += 1
        if definition != "sample.definition":
            raise ActionRejected("RUN_NOT_FOUND")
        return "node-test"

    def graph_factory(self, run, lifecycle):
        self.factory_calls += 1
        if self.factory_hook:
            return self.factory_hook(run, lifecycle)
        return self.engine.assemble(run), {"messages": [{"role": "user", "content": "Synthetic current request"}]}

    @contextmanager
    def session(self, owner):
        yield ExecutionSession(self.runner, lambda run: self.engine.built[run.run_id][1])


class TrustedHost:
    """Test-only substitute for the backend's authenticated context middleware."""

    def __init__(self, app, owner):
        self.app, self.owner = app, owner

    async def __call__(self, scope, receive, send):
        if self.owner is not None:
            scope = {**scope, "a2flow.trusted_context": self.owner}
        await self.app(scope, receive, send)
