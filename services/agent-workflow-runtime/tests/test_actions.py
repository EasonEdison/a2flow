"""Action ingress/evaluation/history checks against explicit synthetic ports."""

from dataclasses import replace
from contextlib import contextmanager
import unittest
from concurrent.futures import ThreadPoolExecutor

from skillweave_contracts import TrustedContext
from skillweave_contracts.models import JsonPointerEqualsPolicy, SchemaValidPolicy
from agent_workflow_runtime import ActionRejected, ActionService
from agent_workflow_runtime.policy import business_succeeded
from support import Configuration, Executor, Repository, context, interaction, request


class ActionServiceTest(unittest.TestCase):
    def setUp(self):
        self.repo, self.config, self.executor = Repository(), Configuration(), Executor()
        self.resumes = []
        self.service = ActionService(
            self.repo, self.config, self.executor,
            lambda item, rid: self.resumes.append((item, rid)),
        )
        self.item = interaction(self.config)
        self.owner = context().trusted_context
        self.service.register(self.item)

    def test_success_requires_executor_result_and_configuration_completion(self):
        self.executor.result = {"accepted": False}
        failed = self.service.submit(request(self.item, "failed"), self.owner)
        self.assertFalse(failed.business_success)
        self.assertFalse(failed.interaction_completed)
        self.assertEqual([], self.resumes)
        self.executor.result = {"accepted": True}
        saved = self.service.submit(
            request(self.item, "save", actionName="save_choice"), self.owner,
        )
        self.assertTrue(saved.business_success)
        self.assertFalse(saved.interaction_completed)
        self.assertEqual([], self.resumes)
        completed = self.service.submit(request(self.item, "complete"), self.owner)
        self.assertTrue(completed.interaction_completed)
        self.assertEqual(1, len(self.resumes))
        self.assertEqual(3, len(self.repo.get(self.item.key).attempts))

    def test_closed_ingress_cannot_claim_identity_or_success(self):
        for field in ("userId", "environment", "businessSuccess", "completed", "runtime"):
            with self.subTest(field=field), self.assertRaises(ActionRejected):
                self.service.submit(request(self.item, **{field: True}), self.owner)
        self.assertEqual([], self.executor.calls)

    def test_ownership_node_run_interaction_and_action_rejected_before_execution(self):
        with self.assertRaisesRegex(ActionRejected, "NOT_AUTHORIZED"):
            self.service.submit(request(self.item), TrustedContext("other-user", "PRT"))
        with self.assertRaisesRegex(ActionRejected, "NOT_AUTHORIZED"):
            self.service.submit(request(self.item), TrustedContext("test-user", "ONLINE"))
        for field in ("runId", "nodeId", "interactionId", "actionName"):
            with self.subTest(field=field), self.assertRaises(ActionRejected):
                self.service.submit(request(self.item, **{field: "wrong"}), self.owner)
        self.assertEqual([], self.executor.calls)

    def test_full_effective_version_closure_is_checked_before_executor(self):
        for index in range(len(self.config.current)):
            current = self.item.recorded_versions
            self.config.current = tuple(
                (key, "new-version" if pos == index else version)
                for pos, (key, version) in enumerate(current)
            )
            with self.assertRaisesRegex(ActionRejected, "RESET_REQUIRED"):
                self.service.submit(request(self.item), self.owner)
        self.assertEqual([], self.executor.calls)

    def test_stopped_and_invalidated_wait_rejected_and_history_retained(self):
        self.repo.save(replace(self.item, run_active=False))
        with self.assertRaisesRegex(ActionRejected, "RUN_STOPPED"):
            self.service.submit(request(self.item), self.owner)
        self.repo.save(replace(self.item, phase="INVALIDATED"))
        with self.assertRaisesRegex(ActionRejected, "INTERACTION_NOT_WAITING"):
            self.service.submit(request(self.item), self.owner)
        self.assertEqual([], self.executor.calls)
        self.assertIsNotNone(self.repo.get(self.item.key))

    def test_input_binding_validator_runs_before_business_call(self):
        for inputs in ({"selection": "unknown"}, {"selection": "left", "userId": "spoof"}):
            with self.assertRaisesRegex(ActionRejected, "INVALID_ACTION_INPUT"):
                self.service.submit(request(self.item, inputs=inputs), self.owner)
        self.assertEqual([], self.executor.calls)

    def test_control_dedup_retains_result_and_rejects_changed_payload(self):
        payload = request(self.item)
        first = self.service.submit(payload, self.owner)
        self.assertEqual(first, self.service.submit(payload, self.owner))
        with self.assertRaisesRegex(ActionRejected, "CONTROL_REQUEST_CONFLICT"):
            self.service.submit(request(self.item, inputs={"selection": "right"}), self.owner)
        self.assertEqual(1, len(self.executor.calls))
        self.assertEqual(1, len(self.resumes))

    def test_concurrent_same_control_under_test_port_executes_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda _: self.service.submit(request(self.item), self.owner), range(2),
            ))
        self.assertTrue(all(item.business_success for item in results))
        self.assertTrue(all(item.resume_status in {"DISPATCHING", "RETURNED"} for item in results))
        self.assertEqual(1, len(self.executor.calls))

    def test_new_control_request_does_not_claim_business_exactly_once(self):
        self.executor.result = {"accepted": False}
        self.service.submit(request(self.item, "first"), self.owner)
        self.service.submit(request(self.item, "second"), self.owner)
        self.assertEqual(2, len(self.executor.calls))

    def test_late_success_after_stop_is_saved_without_resume(self):
        self.executor.hook = lambda: self.repo.save(replace(
            self.repo.get(self.item.key), run_active=False,
        ))
        with self.assertRaisesRegex(ActionRejected, "RUN_STOPPED"):
            self.service.submit(request(self.item), self.owner)
        self.assertTrue(self.repo.get(self.item.key).attempts[-1].business_success)
        self.assertEqual([], self.resumes)

    def test_version_change_during_execution_saves_outcome_without_resume(self):
        self.executor.hook = lambda: setattr(
            self.config, "current", (("APPLICATION:sample.interactive.route-selection", "new"),),
        )
        with self.assertRaisesRegex(ActionRejected, "RESET_REQUIRED"):
            self.service.submit(request(self.item), self.owner)
        self.assertTrue(self.repo.get(self.item.key).attempts[-1].business_success)
        self.assertEqual([], self.resumes)

    def test_executor_exception_is_redacted_and_duplicate_never_reexecutes(self):
        def fail():
            raise RuntimeError("synthetic-sensitive-executor-detail")
        self.executor.hook = fail
        first = self.service.submit(request(self.item), self.owner)
        self.assertEqual("EXECUTION_UNCONFIRMED", first.status)
        self.assertEqual(first, self.service.submit(request(self.item), self.owner))
        self.assertNotIn("synthetic-sensitive", repr(first))
        self.assertEqual(1, len(self.executor.calls))

    def test_resume_failure_does_not_repeat_business_call(self):
        def fail(item, rid):
            raise RuntimeError("synthetic-resume-error")
        self.service.continuation = fail
        with self.assertRaisesRegex(ActionRejected, "RESUME_UNCONFIRMED"):
            self.service.submit(request(self.item), self.owner)
        repeated = self.service.submit(request(self.item), self.owner)
        self.assertEqual("UNCONFIRMED", repeated.resume_status)
        self.assertTrue(repeated.business_success)
        self.assertTrue(repeated.interaction_completed)
        self.assertEqual(1, len(self.executor.calls))

    def test_success_does_not_require_reentrant_repository_scope(self):
        class NonReentrantRepository(Repository):
            entered = False

            @contextmanager
            def scope(self, owner, run_id):
                if self.entered:
                    raise AssertionError("nested repository scope")
                self.entered = True
                try:
                    yield
                finally:
                    self.entered = False

        repo = NonReentrantRepository()
        service = ActionService(repo, self.config, self.executor, lambda item, rid: None)
        service.register(self.item)
        outcome = service.submit(request(self.item), self.owner)
        self.assertEqual("RETURNED", outcome.resume_status)
        self.assertEqual(1, len(self.executor.calls))

    def test_pointer_equality_is_typed_and_missing_does_not_equal_null(self):
        config = self.config.action(self.item, "confirm_route_choice")
        self.assertFalse(business_succeeded(config, {"accepted": 1}))
        self.assertTrue(business_succeeded(config, {"accepted": True}))
        config = replace(config, validate_result=lambda value: True,
                         success_policy=JsonPointerEqualsPolicy("p", "/a~1b/~0key/0", None))
        self.assertTrue(business_succeeded(config, {"a/b": {"~key": [None]}}))
        self.assertFalse(business_succeeded(config, {"a/b": {"~key": []}}))
        config = replace(config, success_policy=SchemaValidPolicy("schema"),
                         validate_result=lambda value: False)
        self.assertFalse(business_succeeded(config, {"accepted": True}))
