"""AF04 offline safety wiring checks. No Docker, PG, credentials or sudo."""

from contextlib import redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from runtime_phase1 import runtime03_pg_window as shared
from runtime_phase1 import runtime04_pg_window as window


class Runtime04WindowTest(unittest.TestCase):
    def test_af04_isolated_spec_does_not_mutate_af03_targets(self):
        self.assertEqual("a2flow-runtime03-pg", shared.window_spec().container)
        self.assertEqual("a2flow-runtime04-pg", shared.window_spec(window.SPEC).container)
        self.assertNotEqual(shared.window_spec().private, window.SPEC.private)
        self.assertNotEqual(shared.window_spec().env_prefix, window.SPEC.env_prefix)
        self.assertEqual("test_postgres_lifecycle_integration.py", window.SPEC.test_pattern)

    def test_cleanup_and_log_checks_receive_same_exact_af04_spec_after_failure(self):
        for failure in (RuntimeError("owned process failure"), ProcessLookupError()):
            with patch.object(shared, "stop_owned_group", side_effect=failure) as stop,\
                 patch.object(shared, "credential_log_check") as logs,\
                 patch.object(shared, "cleanup") as cleanup:
                with self.assertRaises(type(failure)):
                    shared.finish_window(None, "marker", ["synthetic"], window=window.SPEC)
                self.assertEqual(window.SPEC, stop.call_args.kwargs["window"])
                self.assertEqual(window.SPEC, logs.call_args.kwargs["window"])
                cleanup.assert_called_once_with(window=window.SPEC)

    def test_cli_missing_wrong_or_dirty_fixed_source_cannot_start_window(self):
        for expected, actual, dirty in (
            (None, "a" * 40, ""), ("not-sha", "a" * 40, ""),
            ("a" * 40, "b" * 40, ""), ("a" * 40, "a" * 40, " M owned.py"),
        ):
            output = io.StringIO()
            with patch.object(shared, "command", side_effect=[
                SimpleNamespace(stdout=actual), SimpleNamespace(stdout=dirty),
            ]), patch.object(shared, "run_window") as run, redirect_stdout(output):
                args = ["--authorized-window"]
                if expected is not None:
                    args += ["--expected-source-sha", expected]
                self.assertEqual(1, window.main(args))
                run.assert_not_called()

    def test_cli_passes_exact_spec_and_verifies_source_again_after_cleanup(self):
        with patch.object(window, "verify_source", return_value="a" * 40) as verify,\
             patch.object(shared, "run_window") as run, redirect_stdout(io.StringIO()):
            self.assertEqual(0, window.main(["--authorized-window", "--expected-source-sha", "a" * 40]))
        run.assert_called_once_with(window=window.SPEC)
        self.assertEqual(2, verify.call_count)

    def test_cleanup_selects_only_af04_names_without_starting(self):
        with patch.object(shared, "cleanup") as cleanup, patch.object(shared, "run_window") as run:
            self.assertEqual(0, window.main(["--cleanup"]))
        cleanup.assert_called_once_with(window=window.SPEC)
        run.assert_not_called()
