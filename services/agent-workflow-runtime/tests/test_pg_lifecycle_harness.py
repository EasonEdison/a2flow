"""AF04 real SDK harness in memory only; not PostgreSQL persistence evidence."""

from collections import Counter
from contextlib import nullcontext
import unittest
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver
from agent_workflow_runtime import ActionService
from agent_workflow_runtime.native_control import ControlledRunRunner
from lifecycle_support import fixture
from pg_lifecycle_worker import graph_for
from support import Configuration, Executor, Repository, request


class PgLifecycleHarnessTest(unittest.TestCase):
    def test_exact_pg_graph_shape_reassembles_for_controlled_native_resume(self):
        _, life, run = fixture()
        repo, config, executor = Repository(), Configuration(), Executor()
        service = ActionService(repo, config, executor, None, lifecycle=life)
        runner, saver, calls = ControlledRunRunner(life, None, None), MemorySaver(), Counter()
        with patch("pg_lifecycle_worker.event", side_effect=lambda case, name, amount=1: calls.update({name: amount})):
            graph = graph_for("offline", run, life, saver, service, config)
            waiting = runner.invoke(run, graph, {"messages": [{"role": "user", "content": "Synthetic"}]})
            self.assertEqual(1, len(waiting["__interrupt__"]))
            graph_for("offline", run, life, saver, service, config, resume=True)
            item = next(iter(repo.items.values()))
            completed = runner.action(run, service, request(item))
        self.assertEqual("RETURNED", completed.resume_status)
        self.assertEqual("SUCCEEDED", life.read(run.owner, run.run_id).status)
        self.assertEqual(1, len(executor.calls))
        self.assertEqual({"skill": 1, "native_resume": 1, "finalizer": 1, "successor": 1}, dict(calls))

    def test_restart_process_factory_uses_fresh_state_without_old_context(self):
        import pg_lifecycle_worker as worker
        runs, old_life, old = fixture()
        old_life.stop(old.owner, old.run_id, "stop")
        runs.forbid_run_read.add(old.run_id)
        runs.forbid_fact_read.add(old.run_id)
        calls, repo, executor, config = Counter(), Repository(), Executor(), Configuration()
        def service(case, run, life, **kwargs):
            self.assertEqual(old.run_id, kwargs["forbidden"])
            return repo, config, ActionService(repo, config, executor, None, lifecycle=life)
        with patch.object(worker, "DEFINITION", old.definition_key), \
             patch.object(worker, "conninfo", return_value="unused-offline"), \
             patch.object(worker, "NoOldRunRepository", return_value=runs), \
             patch.object(worker.NoOldSaver, "from_conn_string", return_value=nullcontext(MemorySaver())), \
             patch.object(worker, "service_for", side_effect=service), \
             patch.object(worker, "event", side_effect=lambda case, name, amount=1: calls.update({name: amount})):
            options = {"source": old.run_id, "old_thread": old.thread_id}
            first = worker.main("restart", "offline", options)
            second = worker.main("restart", "offline", options)
        self.assertEqual(first["runId"], second["runId"])
        self.assertNotEqual(old.run_id, first["runId"])
        self.assertEqual({"factory": 1, "skill": 1}, dict(calls))
        self.assertEqual(1, len(repo.items))

    def test_old_pg_read_spies_fail_before_any_connection_is_needed(self):
        import pg_lifecycle_worker as worker
        with patch.object(worker, "conninfo", return_value="unused-offline"):
            repo = worker.NoOldRunRepository("old-run")
            interactions = worker.NoOldInteractions("old-run")
        with self.assertRaisesRegex(AssertionError, "old full Run"):
            repo.get_run(worker.OWNER, "old-run")
        with self.assertRaisesRegex(AssertionError, "old operation"):
            repo.operations(worker.OWNER, "old-run")
        with self.assertRaisesRegex(AssertionError, "old interaction"):
            interactions.for_run(worker.OWNER, "old-run")
        saver = object.__new__(worker.NoOldSaver)
        saver.forbidden_thread = "old-thread"
        with self.assertRaisesRegex(AssertionError, "old checkpoint"):
            saver.get_tuple({"configurable": {"thread_id": "old-thread"}})
        with self.assertRaisesRegex(AssertionError, "unscoped checkpoint"):
            saver.list(None)


class OwnedChildCleanupTest(unittest.TestCase):
    def test_cleanup_is_registered_before_allocate_set_up_can_fail(self):
        from unittest.mock import Mock
        import test_postgres_lifecycle_integration as pgtests
        case = pgtests.PostgresLifecycleProcessTest(
            "test_no_card_stop_owner_environment_and_dedup_are_cross_process")
        child = Mock()
        child.poll.return_value = None
        def failed_allocate(*args):
            case.children.append(child)
            raise RuntimeError("synthetic allocate failure")
        with patch.object(case, "call", side_effect=failed_allocate):
            with self.assertRaises(RuntimeError):
                case.setUp()
        self.assertTrue(case.doCleanups())
        child.terminate.assert_called_once()
        child.communicate.assert_called_once_with(timeout=5)

    def test_timeout_kills_and_reaps_exact_child_then_cleans_remaining_children(self):
        import subprocess
        from unittest.mock import Mock, call
        import test_postgres_lifecycle_integration as pgtests
        first, second = Mock(), Mock()
        first.poll.return_value = second.poll.return_value = None
        first.communicate.side_effect = [subprocess.TimeoutExpired("owned", 5), ("", "")]
        pgtests.cleanup_children([first, second])
        first.terminate.assert_called_once()
        first.kill.assert_called_once()
        self.assertEqual([call(timeout=5), call(timeout=5)], first.communicate.call_args_list)
        second.terminate.assert_called_once()
        second.communicate.assert_called_once_with(timeout=5)

    def test_failed_terminate_or_reap_does_not_skip_other_owned_children(self):
        import subprocess
        from unittest.mock import Mock
        import test_postgres_lifecycle_integration as pgtests
        for phase in ("terminate", "reap", "wait_fatal"):
            with self.subTest(phase=phase):
                first, second = Mock(), Mock()
                first.poll.return_value = second.poll.return_value = None
                if phase == "terminate":
                    first.terminate.side_effect = RuntimeError("synthetic termination failure")
                elif phase == "reap":
                    first.communicate.side_effect = subprocess.TimeoutExpired("owned", 5)
                else:
                    first.communicate.side_effect = [KeyboardInterrupt("synthetic"), ("", "")]
                expected = KeyboardInterrupt if phase == "wait_fatal" else (RuntimeError, subprocess.TimeoutExpired)
                with self.assertRaises(expected):
                    pgtests.cleanup_children([first, second])
                self.assertTrue(first.communicate.called)
                second.terminate.assert_called_once()
                second.communicate.assert_called_once_with(timeout=5)
