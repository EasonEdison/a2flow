"""Offline safety checks for the prepared MVP08 live window."""

from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from runtime_phase1 import runtime03_pg_window as shared
from runtime_phase1 import runtime08_mvp_window as window


class Runtime08WindowTest(unittest.TestCase):
    def test_spec_is_exact_and_does_not_mutate_prior_windows(self):
        self.assertEqual("a2flow-runtime03-pg", shared.window_spec().container)
        self.assertEqual("a2flow-mvp08-pg", window.SPEC.container)
        self.assertEqual("a2flow-mvp08-pgdata", window.SPEC.volume)
        self.assertEqual(
            Path("/home/admin/OpenSource/.tmp/a2flow-mvp08-live"),
            window.SPEC.private,
        )
        self.assertEqual("experiments/runtime-phase1/tests", window.SPEC.test_directory)
        self.assertEqual("test_mvp08_live_acceptance.py", window.SPEC.test_pattern)
        self.assertEqual(300, window.SPEC.max_seconds)
        self.assertEqual(256 * 1024, window.SPEC.max_data_kib)
        self.assertIn("packages/asset-store/src", window.SPEC.pythonpath)
        self.assertEqual(window.EVIDENCE_FILE, window.SPEC.evidence_file)
        self.assertEqual("AF-MVP-08-LIVE-W3", window.WINDOW_NAME)
        self.assertEqual(
            Path("/home/admin/OpenSource/.evidence/oss-agent-workflow-runtime/"
                 "af-mvp-08-live-w3.jsonl"),
            window.EVIDENCE_FILE,
        )

    def test_model_key_file_requires_exact_private_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory).resolve() / "model-key"
            key.write_text("synthetic-not-a-real-key")
            key.chmod(0o600)
            with patch.dict(os.environ, {
                window.MODEL_KEY_FILE_ENV: str(key),
            }, clear=True):
                self.assertEqual(key, window.verified_model_key_file())

            key.chmod(0o644)
            with patch.dict(os.environ, {
                window.MODEL_KEY_FILE_ENV: str(key),
            }, clear=True), self.assertRaisesRegex(RuntimeError, "MODEL_KEY_FILE_UNSAFE"):
                window.verified_model_key_file()

    def test_direct_secret_environment_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            key = root / "key"
            key.write_text("synthetic-not-a-real-key")
            key.chmod(0o600)
            link = root / "link"
            link.symlink_to(key)
            for values, code in (
                ({
                    window.MODEL_KEY_FILE_ENV: str(key),
                    "DEEPSEEK_API_KEY": "synthetic",
                }, "DIRECT_MODEL_SECRET_ENV_FORBIDDEN"),
                ({window.MODEL_KEY_FILE_ENV: str(link)}, "MODEL_KEY_FILE_UNSAFE"),
                ({}, "MODEL_KEY_FILE_REQUIRED"),
            ):
                with self.subTest(code=code), patch.dict(os.environ, values, clear=True),\
                        self.assertRaisesRegex(RuntimeError, code):
                    window.verified_model_key_file()

    def test_custom_window_budget_stops_on_time_or_data(self):
        volume = "/task-owned-volume"
        with patch.object(shared, "memory", return_value=(1024 * 1024, 0)),\
             patch.object(shared.time, "monotonic", return_value=301),\
             self.assertRaisesRegex(RuntimeError, "resource/time"):
            shared.check_budget(0, 0, volume, window=window.SPEC)

        spec = replace(window.SPEC, max_seconds=900, max_data_kib=10)
        with patch.object(shared, "memory", return_value=(1024 * 1024, 0)),\
             patch.object(shared.time, "monotonic", return_value=1),\
             patch.object(shared, "command",
                          return_value=SimpleNamespace(stdout="11 /task-owned-volume\n")),\
             self.assertRaisesRegex(RuntimeError, "data size"):
            shared.check_budget(0, 0, volume, window=spec)

    def test_missing_wrong_or_dirty_source_cannot_start(self):
        for expected, actual, dirty in (
            (None, "a" * 40, ""),
            ("not-sha", "a" * 40, ""),
            ("a" * 40, "b" * 40, ""),
            ("a" * 40, "a" * 40, " M owned.py"),
        ):
            output = io.StringIO()
            with patch.object(shared, "command", side_effect=[
                SimpleNamespace(stdout=actual),
                SimpleNamespace(stdout=dirty),
            ]), patch.object(shared, "run_window") as run, redirect_stdout(output):
                args = ["--authorized-window"]
                if expected is not None:
                    args += ["--expected-source-sha", expected]
                self.assertEqual(1, window.main(args))
                run.assert_not_called()

    def test_authorized_path_checks_key_and_source_around_shared_window(self):
        source = "a" * 40
        key = Path("/private/model-key")
        with patch.object(window, "verify_source", return_value=source) as verify,\
             patch.object(window, "verified_model_key_file", return_value=key) as key_check,\
             patch.object(window, "prepare_evidence",
                          return_value=window.EVIDENCE_FILE) as prepare,\
             patch.object(shared, "run_window") as run,\
             patch.object(shared, "append_evidence") as append,\
             patch.dict(os.environ, {}, clear=True),\
             redirect_stdout(io.StringIO()):
            self.assertEqual(0, window.main([
                "--authorized-window",
                "--expected-source-sha",
                source,
            ]))
        key_check.assert_called_once_with()
        prepare.assert_called_once_with(source)
        run.assert_called_once_with(window=window.SPEC)
        append.assert_called_once_with(
            "WINDOW_RESULT", window=window.SPEC, outcome="PASS",
        )
        self.assertEqual(2, verify.call_count)

    def test_cleanup_is_exact_and_needs_no_key_or_source(self):
        with patch.object(shared, "cleanup") as cleanup,\
             patch.object(shared, "run_window") as run,\
             patch.dict(os.environ, {}, clear=True):
            self.assertEqual(0, window.main(["--cleanup"]))
        cleanup.assert_called_once_with(window=window.SPEC)
        run.assert_not_called()

    def test_failed_child_still_persists_safe_cleanup_result(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory).resolve() / "evidence.jsonl"
            evidence.touch(mode=0o600)
            spec = replace(window.SPEC, evidence_file=evidence)
            shared.append_evidence(
                "LIVE_RESULT", window=spec, outcome="FAILED",
                errorStage="ACTION_REQUEST", errorType="RuntimeError", modelCalls=3,
            )
            with patch.object(
                    shared, "stop_owned_group",
                    side_effect=RuntimeError("synthetic-secret-must-not-persist"),
            ), patch.object(shared, "credential_log_check"),\
                    patch.object(shared, "cleanup") as cleanup,\
                    self.assertRaisesRegex(RuntimeError, "synthetic-secret"):
                shared.finish_window(None, "marker", ["not-written"], window=spec)
            cleanup.assert_called_once_with(window=spec)
            records = [json.loads(line) for line in evidence.read_text().splitlines()]
            self.assertEqual(["LIVE_RESULT", "CLEANUP_RESULT"], [
                record["stage"] for record in records
            ])
            self.assertEqual("PASS", records[-1]["outcome"])
            self.assertNotIn("synthetic-secret", evidence.read_text())


if __name__ == "__main__":
    unittest.main()
