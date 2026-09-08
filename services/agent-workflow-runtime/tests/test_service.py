"""Formal service boundary tests; injected fixtures remain outside production."""

import ast
from pathlib import Path
import unittest

from agent_workflow_runtime.models import ActionRejected
from service_support import ServiceFixture


class ServiceTest(unittest.TestCase):
    def test_production_imports_never_depend_on_experiments(self):
        root = Path(__file__).resolve().parents[1] / "src" / "agent_workflow_runtime"
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith(("runtime_phase1", "experiments", "test_")), path)
                elif isinstance(node, ast.Import):
                    self.assertTrue(all(not a.name.startswith(("runtime_phase1", "experiments", "test_")) for a in node.names), path)

    def test_missing_trusted_context_never_calls_backend_factories(self):
        fixture = ServiceFixture()
        for method, args in (
            (fixture.service.start, ("id", "sample.definition", {})),
            (fixture.service.inspect, ("run-test",)),
            (fixture.service.control, ("id",)),
            (fixture.service.stop, ("run-test", "id")),
            (fixture.service.restart, ("run-test", "id", {})),
            (fixture.service.action, ("run-test", "node-test", {})),
        ):
            with self.assertRaisesRegex(ActionRejected, "TRUSTED_CONTEXT_REQUIRED"):
                method(None, *args)
        self.assertEqual(0, fixture.entry_calls)
        self.assertEqual(0, fixture.factory_calls)

    def test_read_control_never_runs_resolver_or_execution_session(self):
        fixture = ServiceFixture()
        run = fixture.engine.run
        fixture.service.resolve_entry = lambda *a: self.fail("GET called resolver")
        fixture.service.execution_session = lambda *a: self.fail("GET constructed execution session")
        value = fixture.service.control(fixture.owner, run.initial_control_id)
        self.assertEqual(run.run_id, value["runId"])
        self.assertEqual(0, fixture.factory_calls)
