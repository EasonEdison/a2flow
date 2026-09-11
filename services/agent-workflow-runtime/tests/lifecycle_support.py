"""Transactional in-memory test adapter. Never a production DB fallback."""

from contextlib import contextmanager
from copy import deepcopy
from threading import RLock

from agent_workflow_runtime.lifecycle import RunLifecycle, RunRecord, RunControl, OperationFact
from agent_workflow_runtime.postgres_lifecycle import encode_record, decode_record


class RunRepository:
    def __init__(self):
        self.runs, self.controls, self.facts = {}, {}, {}
        self.lock = RLock()
        self.commits = 0
        self.forbid_run_read = set()
        self.forbid_fact_read = set()
        self.scope_depth = 0

    @contextmanager
    def transaction(self):
        with self.lock:
            before = deepcopy((self.runs, self.controls, self.facts))
            self.scope_depth += 1
            try:
                yield
                self.commits += 1
            except BaseException:
                self.runs, self.controls, self.facts = before
                raise
            finally:
                self.scope_depth -= 1

    def run_scope(self, owner, run_id):
        return self.transaction()

    def control_scope(self, owner, control_id):
        return self.transaction()

    def get_run(self, owner, run_id, *, for_update=False):
        if run_id in self.forbid_run_read:
            raise AssertionError("old full context must not be read")
        raw = self.runs.get((owner, run_id))
        return None if raw is None else decode_record(raw, RunRecord)

    def restart_identity(self, owner, run_id):
        raw = self.runs.get((owner, run_id))
        if raw is None:
            return None
        return {"runId": run_id, "status": raw["status"], "definitionKey": raw["definition_key"]}

    def put_run(self, run):
        self.runs[(run.owner, run.run_id)] = encode_record(run)

    def get_control(self, owner, control_id):
        raw = self.controls.get((owner, control_id))
        return None if raw is None else decode_record(raw, RunControl)

    def put_control(self, owner, control):
        self.controls[(owner, control.control_id)] = encode_record(control)

    def get_operation(self, owner, run_id, operation_id):
        if run_id in self.forbid_fact_read:
            raise AssertionError("old operation facts must not be read")
        raw = self.facts.get((owner, run_id, operation_id))
        return None if raw is None else decode_record(raw, OperationFact)

    def put_operation(self, owner, run_id, fact):
        self.facts[(owner, run_id, fact.operation_id)] = encode_record(fact)

    def operations(self, owner, run_id):
        if run_id in self.forbid_fact_read:
            raise AssertionError("old operation facts must not be read")
        return tuple(decode_record(raw, OperationFact)
                     for (who, rid, _), raw in self.facts.items() if who == owner and rid == run_id)


def fixture():
    from support import context
    repository = RunRepository()
    lifecycle = RunLifecycle(repository)
    owner = context().trusted_context
    run, _ = lifecycle.allocate(owner, "initial-start", "sample.definition", {"fresh": True},
                                "node-test", lambda *_: (("WORKFLOW:sample", "v1"),))
    return repository, lifecycle, run
