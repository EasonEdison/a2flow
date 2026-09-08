"""Offline injected-fault checks only; no Docker, PG, secrets or sudo executed."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from runtime_phase1 import runtime03_pg_window as window


class WindowCleanupTest(unittest.TestCase):
    def test_cleanup_runs_when_process_or_log_checks_raise(self):
        for failure in (RuntimeError("owned worker residual"), ProcessLookupError(),
                        subprocess.TimeoutExpired("owned-worker", 5)):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(window, "stop_owned_group", side_effect=failure), \
                     patch.object(window, "credential_log_check") as logs, \
                     patch.object(window, "cleanup") as cleanup:
                    with self.assertRaises(type(failure)):
                        window.finish_window(Mock(), "owned-marker", ["synthetic"])
                    logs.assert_called_once()
                    cleanup.assert_called_once()
        with patch.object(window, "stop_owned_group"), \
             patch.object(window, "credential_log_check", side_effect=RuntimeError()), \
             patch.object(window, "cleanup") as cleanup:
            with self.assertRaises(RuntimeError):
                window.finish_window(None, "owned-marker", ["synthetic"])
            cleanup.assert_called_once()

    def test_exited_parent_still_checks_group_and_tolerates_exit_race(self):
        child = Mock(pid=12345)
        child.poll.return_value = 0
        with patch.object(window, "group_members", side_effect=[[12346], []]) as members, \
             patch.object(window.os, "killpg", side_effect=ProcessLookupError()) as kill:
            window.stop_owned_group(child, "unique-marker")
        kill.assert_called_once_with(12345, window.signal.SIGTERM)
        self.assertTrue(all(call.args == (12345, "unique-marker") for call in members.call_args_list))
        child.communicate.assert_called_once_with(timeout=5)

    def test_two_communicate_timeouts_report_residual(self):
        child = Mock(pid=12345)
        child.communicate.side_effect = subprocess.TimeoutExpired("owned", 5)
        with patch.object(window, "group_members", return_value=[12345]), \
             patch.object(window.os, "killpg") as kill:
            with self.assertRaisesRegex(RuntimeError, "OWNED_TEST_PROCESS_RESIDUAL"):
                window.stop_owned_group(child, "unique-marker")
        self.assertEqual(2, kill.call_count)
        self.assertEqual(2, child.communicate.call_count)

    def socket_case(self, delete):
        # PermissionError models PG UID999 taking directory ownership/mode. This
        # is a fault fixture, not a claim that a live container was launched.
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory) / "private"
            private.mkdir()
            (private / ".owner").write_text(window.OWNER)
            socket = private / "socket"
            socket.mkdir()
            (socket / ".s.PGSQL.5432").touch()
            real_remove = shutil.rmtree

            def remove(path, *args, **kwargs):
                if path == socket:
                    raise PermissionError("simulated PG-owned socket directory")
                return real_remove(path, *args, **kwargs)

            def privileged(args, **kwargs):
                self.assertEqual(["sudo", "-n", "rm", "-r", "--one-file-system", "--", str(socket)], args)
                if delete:
                    real_remove(socket)

            with patch.object(window, "PRIVATE", private), \
                 patch.object(window, "inspect", return_value=None), \
                 patch.object(window.shutil, "rmtree", side_effect=remove), \
                 patch.object(window, "command", side_effect=privileged) as command, \
                 redirect_stdout(io.StringIO()):
                if delete:
                    window.cleanup()
                    self.assertFalse(private.exists())
                else:
                    with self.assertRaisesRegex(RuntimeError, "CLEANUP_SOCKET_RESIDUAL"):
                        window.cleanup()
                    self.assertTrue(socket.exists())
                command.assert_called_once()

    def test_pg_owned_socket_uses_only_exact_validated_privileged_subtree(self):
        self.socket_case(True)

    def test_socket_cleanup_residual_is_explicit_not_false_success(self):
        self.socket_case(False)

    def test_container_logs_are_checked_without_echoing_plaintext(self):
        target = {"Config": {"Labels": {"a2flow.owner": window.OWNER}}}
        for raw, passed in (("safe log", True), ("synthetic-secret-A", False),
                            ("synthetic-secret-B", False)):
            output = io.StringIO()
            with patch.object(window, "inspect", return_value=target), \
                 patch.object(window, "docker", return_value=SimpleNamespace(returncode=0, stdout=raw, stderr="")), \
                 redirect_stdout(output):
                if passed:
                    window.credential_log_check(["synthetic-secret-A", "synthetic-secret-B"])
                else:
                    with self.assertRaisesRegex(RuntimeError, "CREDENTIAL_LOG_CHECK_FAILED"):
                        window.credential_log_check(["synthetic-secret-A", "synthetic-secret-B"])
            self.assertIn("PASS" if passed else "FAIL", output.getvalue())
            self.assertNotIn("synthetic-secret", output.getvalue())
