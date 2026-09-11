"""Credential-safety tests for the PostgreSQL probe bootstrap."""

from pathlib import Path
import tempfile
import unittest

from runtime_phase1.postgres_parallel_probe import (
    ProbeBootstrapError,
    bootstrap_probe_database,
)


SCRAM_VERIFIER = (
    "SCRAM-SHA-256$4096:c3ludGhldGljLXNhbHQ="
    "$c3RvcmVkLWtleQ==:c2VydmVyLWtleQ=="
)


class RecordingCursor:
    """Record SQL text separately from ordinary bound parameters."""

    def __init__(
        self,
        exists_results: list[bool],
        *,
        fail_fragment: str | None = None,
        failure_text: str = "",
    ) -> None:
        self._exists_results = iter(exists_results)
        self._fail_fragment = fail_fragment
        self._failure_text = failure_text
        self.executions: list[tuple[object, object]] = []

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def execute(self, statement: object, params: object = None) -> None:
        self.executions.append((statement, params))
        if (
            self._fail_fragment
            and self._fail_fragment in str(statement)
        ):
            raise RuntimeError(self._failure_text)

    def fetchone(self) -> tuple[bool]:
        return (next(self._exists_results),)


class RecordingPgConnection:
    """Expose the libpq password-encryption surface used by the probe."""

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, bytes, bytes]] = []

    def encrypt_password(
        self,
        password: bytes,
        user: bytes,
        algorithm: bytes,
    ) -> bytes:
        self.calls.append((password, user, algorithm))
        return SCRAM_VERIFIER.encode("ascii")


class RecordingConnection:
    """Minimal context-managed connection for bootstrap tests."""

    class Info:
        encoding = "utf-8"

    def __init__(self, cursor: RecordingCursor) -> None:
        self._cursor = cursor
        self.info = self.Info()
        self.pgconn = RecordingPgConnection()

    def __enter__(self) -> "RecordingConnection":
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def cursor(self) -> RecordingCursor:
        return self._cursor


class RecordingConnectionFactory:
    """Return predetermined connections and record only call structure."""

    def __init__(self, connections: list[RecordingConnection]) -> None:
        self._connections = iter(connections)
        self.calls = 0

    def __call__(self, connection_string: str, **kwargs: object) -> object:
        del connection_string, kwargs
        self.calls += 1
        return next(self._connections)


def _statement_text(*cursors: RecordingCursor) -> str:
    return "\n".join(
        str(statement)
        for cursor in cursors
        for statement, _ in cursor.executions
    )


class PostgresBootstrapCredentialTest(unittest.TestCase):
    """Catch plaintext credentials, LOGIN-before-ready, and unsafe claims."""

    def test_bootstrap_sends_only_scram_verifier_in_password_ddl(self) -> None:
        sentinel = "SYNTHETIC_SECRET_MUST_NOT_APPEAR"
        cursor = RecordingCursor([False, False])
        connection = RecordingConnection(cursor)
        factory = RecordingConnectionFactory([connection])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            admin_password_file = root / "admin_password"
            probe_password_file = root / "probe_password"
            admin_password_file.write_text("synthetic-admin", encoding="utf-8")
            probe_password_file.write_text(sentinel, encoding="utf-8")

            bootstrap_probe_database(
                root / "socket",
                admin_password_file,
                probe_password_file,
                connection_factory=factory,
                connection_limit=8,
            )

        statement_text = _statement_text(cursor)
        self.assertIn("CREATE ROLE runtime_probe NOLOGIN", statement_text)
        self.assertIn("CONNECTION LIMIT 8", statement_text)
        self.assertIn("SCRAM-SHA-256", statement_text)
        self.assertNotIn(sentinel, statement_text)
        self.assertEqual(
            [
                (
                    sentinel.encode("utf-8"),
                    b"runtime_probe",
                    b"scram-sha-256",
                )
            ],
            connection.pgconn.calls,
        )
        self.assertEqual(1, factory.calls)

    def test_failure_disables_role_and_redacts_observable_error(self) -> None:
        sentinel = "SYNTHETIC_SECRET_MUST_NOT_APPEAR"
        failed_cursor = RecordingCursor(
            [False, False],
            fail_fragment="CREATE DATABASE",
            failure_text=f"database echoed {sentinel}",
        )
        disabled_cursor = RecordingCursor([True])
        factory = RecordingConnectionFactory(
            [
                RecordingConnection(failed_cursor),
                RecordingConnection(disabled_cursor),
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            admin_password_file = root / "admin_password"
            probe_password_file = root / "probe_password"
            admin_password_file.write_text("synthetic-admin", encoding="utf-8")
            probe_password_file.write_text(sentinel, encoding="utf-8")

            with self.assertLogs(
                "runtime_phase1.postgres_parallel_probe",
                level="ERROR",
            ) as logs:
                with self.assertRaises(ProbeBootstrapError) as raised:
                    bootstrap_probe_database(
                        root / "socket",
                        admin_password_file,
                        probe_password_file,
                        connection_factory=factory,
                    )

            self.assertFalse(probe_password_file.exists())

        observable_text = (
            _statement_text(failed_cursor, disabled_cursor)
            + "\n".join(logs.output)
            + str(raised.exception)
        )
        self.assertNotIn(sentinel, observable_text)
        self.assertIn("credentialState=ROLE_DISABLED", str(raised.exception))
        self.assertEqual(2, factory.calls)

    def test_disable_failure_is_unsafe_unknown_not_invalidated(self) -> None:
        sentinel = "SYNTHETIC_SECRET_MUST_NOT_APPEAR"
        first_cursor = RecordingCursor(
            [True],
            fail_fragment="ALTER ROLE runtime_probe NOLOGIN",
            failure_text=f"first failure echoed {sentinel}",
        )
        disable_cursor = RecordingCursor(
            [True],
            fail_fragment="ALTER ROLE runtime_probe NOLOGIN",
            failure_text=f"disable failure echoed {sentinel}",
        )
        factory = RecordingConnectionFactory(
            [
                RecordingConnection(first_cursor),
                RecordingConnection(disable_cursor),
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            admin_password_file = root / "admin_password"
            probe_password_file = root / "probe_password"
            admin_password_file.write_text("synthetic-admin", encoding="utf-8")
            probe_password_file.write_text(sentinel, encoding="utf-8")

            with self.assertLogs(
                "runtime_phase1.postgres_parallel_probe",
                level="ERROR",
            ) as logs:
                with self.assertRaises(ProbeBootstrapError) as raised:
                    bootstrap_probe_database(
                        root / "socket",
                        admin_password_file,
                        probe_password_file,
                        connection_factory=factory,
                    )

            self.assertFalse(probe_password_file.exists())

        observable_text = "\n".join(logs.output) + str(raised.exception)
        self.assertNotIn(sentinel, observable_text)
        self.assertIn("credentialState=UNSAFE_UNKNOWN", str(raised.exception))
        self.assertIn("destroy isolated PostgreSQL", str(raised.exception))
        self.assertNotIn("invalidated", observable_text)
        self.assertEqual(2, factory.calls)
