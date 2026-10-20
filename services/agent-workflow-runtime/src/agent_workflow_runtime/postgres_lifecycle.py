"""Run row locks use their own short transactions, never AF03 savepoints."""

from contextlib import contextmanager
from collections.abc import Callable
from typing import Any
from dataclasses import asdict, fields
from threading import local

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from skillweave_contracts import TrustedContext

from .lifecycle import RunRecord, RunControl, OperationFact, canonical
from .models import ActionRejected
from .postgres import lock_key
from .workflow_attention import DDL as ATTENTION_DDL
from .events import DomainEvent

TransactionalEventWriter = Callable[[psycopg.Connection[Any], DomainEvent], None]


DDL = (
    """CREATE TABLE IF NOT EXISTS runtime_runs (
        user_id BIGINT NOT NULL, environment TEXT NOT NULL, run_id TEXT NOT NULL,
        thread_id TEXT NOT NULL UNIQUE, document JSONB NOT NULL,
        PRIMARY KEY (user_id, environment, run_id))""",
    """CREATE TABLE IF NOT EXISTS runtime_run_controls (
        user_id BIGINT NOT NULL, environment TEXT NOT NULL, control_id TEXT NOT NULL,
        document JSONB NOT NULL, PRIMARY KEY (user_id, environment, control_id))""",
    """CREATE TABLE IF NOT EXISTS runtime_operation_facts (
        user_id BIGINT NOT NULL, environment TEXT NOT NULL, run_id TEXT NOT NULL,
        operation_id TEXT NOT NULL, document JSONB NOT NULL,
        PRIMARY KEY (user_id, environment, run_id, operation_id),
        FOREIGN KEY (user_id, environment, run_id) REFERENCES runtime_runs)""",
)


def decode_record(value, cls):
    try:
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)} | {"schemaVersion"}:
            raise ValueError()
        if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
            raise ValueError()
        data = {key: item for key, item in value.items() if key != "schemaVersion"}
        if cls is RunRecord:
            data["owner"] = TrustedContext.from_mapping(data["owner"])
            versions = data["versions"]
            if type(versions) is not list or not versions:
                raise ValueError()
            if any(type(p) is not list or len(p) != 2 or
                   any(type(v) is not str or not v for v in p) for p in versions):
                raise ValueError()
            data["versions"] = tuple(tuple(p) for p in versions)
            if len(dict(data["versions"])) != len(versions):
                raise ValueError()
            if data["status"] not in {"RUNNING", "STOPPED", "SUCCEEDED", "FAILED"}:
                raise ValueError()
            if type(data["revision"]) is not int or data["revision"] < 0:
                raise ValueError()
        elif cls is RunControl:
            if data["status"] not in {"DISPATCHING", "RETURNED", "UNCONFIRMED"}:
                raise ValueError()
        elif cls is OperationFact:
            if data["kind"] not in {"NODE", "ROUTER", "MODEL", "TOOL", "ACTION", "FINALIZER", "RETRY"}:
                raise ValueError()
            if data["status"] not in {"IN_FLIGHT", "RETURNED", "INTERRUPTED", "UNCONFIRMED"}:
                raise ValueError()
            if type(data["admitted_revision"]) is not int or data["admitted_revision"] < 0:
                raise ValueError()
            if (data["status"] == "IN_FLIGHT") != (data["result_json"] is None):
                raise ValueError()
        else:
            raise ValueError()
        for name, item in data.items():
            if name.endswith("_json"):
                import json
                if item is not None and (type(item) is not str or canonical(json.loads(item)) != item):
                    raise ValueError()
            elif name.endswith("_id") or name in {"definition_key", "kind"}:
                if type(item) is not str or not item or len(item) > 256:
                    raise ValueError()
        record = cls(**data)
        if cls is RunRecord:
            record.context()
        return record
    except Exception:
        raise ActionRejected("INVALID_RUN_RECORD") from None


def encode_record(record):
    import json
    value = asdict(record)
    if isinstance(record, RunRecord):
        value["owner"] = record.owner.to_mapping()
    value["schemaVersion"] = 1
    value = json.loads(canonical(value))
    decode_record(value, type(record))
    return value


class PostgresRunRepository:
    def __init__(self, conninfo, *, connection_factory=psycopg.connect,
                 transactional_event_writer: TransactionalEventWriter | None = None):
        self._conninfo, self._connect = conninfo, connection_factory
        self._local = local()
        self._event_writer = transactional_event_writer

    def publish(self, event: DomainEvent) -> None:
        """Join the lifecycle transaction; independent waiting events use a short one."""
        if self._event_writer is None:
            raise ActionRejected("TRANSACTIONAL_EVENT_WRITER_REQUIRED")
        owner = TrustedContext(user_id=event.user_id, environment=event.environment)
        if getattr(self._local, "connection", None) is not None:
            self._event_writer(self._connection(owner), event)
        else:
            with self._transaction(owner):
                self._event_writer(self._connection(owner), event)

    def waiting_candidates(self, environment: str, *, after=None, limit: int = 3):
        if environment not in {"PRT", "ONLINE"} or not 1 <= limit <= 10:
            raise ActionRejected("INVALID_WAITING_SCAN")
        with self._transaction(None):
            rows = self._connection(None).execute(
                """SELECT r.user_id,r.run_id FROM runtime_runs r
                   WHERE r.environment=%s AND r.document->>'status'='RUNNING'
                     AND (%s::bigint IS NULL OR (r.user_id,r.run_id) > (%s,%s))
                     AND EXISTS (SELECT 1 FROM runtime_interactions i
                         WHERE i.user_id=r.user_id AND i.environment=r.environment
                           AND i.run_id=r.run_id AND i.document->>'phase'='WAITING'
                           AND i.document->>'run_active'='true'
                           AND i.document->>'node_waiting'='true')
                   ORDER BY r.user_id,r.run_id LIMIT %s""",
                (environment, None if after is None else after[0],
                 None if after is None else after[0], "" if after is None else after[1], limit),
            ).fetchall()
            return [(row["user_id"], row["run_id"]) for row in rows]

    def waiting_interaction(self, run: RunRecord, reference: dict[str, str]) -> bool:
        # The caller holds the run lock. Only committed interaction identity authorizes a notice.
        row = self._connection(run.owner).execute(
            """SELECT 1 FROM runtime_interactions
               WHERE user_id=%s AND environment=%s AND run_id=%s AND node_id=%s
                 AND interaction_id=%s AND document->>'phase'='WAITING'
                 AND document->>'run_active'='true' AND document->>'node_waiting'='true'
                 AND document->>'graph_thread_id'=%s AND document->>'application_key'=%s
                 AND document->>'application_version'=%s""",
            (run.owner.user_id, run.owner.environment, run.run_id, reference["nodeId"],
             reference["interactionId"], run.thread_id, reference["applicationKey"],
             reference["versionId"]),
        ).fetchone()
        return row is not None

    @contextmanager
    def _transaction(self, owner):
        if getattr(self._local, "connection", None) is not None:
            raise ActionRejected("NESTED_RUN_TRANSACTION")
        connection = None
        try:
            connection = self._connect(
                self._conninfo, autocommit=True, row_factory=dict_row, connect_timeout=5,
                options="-c lock_timeout=5000 -c statement_timeout=10000",
                application_name="a2flow-runtime04",
            )
            self._local.connection, self._local.owner = connection, owner
            with connection.transaction():
                yield
        except ActionRejected:
            raise
        except Exception:
            # No reconnect; uncertain commit is never reported as accepted stop/start.
            raise ActionRejected("RUN_REPOSITORY_UNCONFIRMED") from None
        finally:
            self._local.connection = None
            self._local.owner = None
            if connection is not None:
                connection.close()

    def _connection(self, owner):
        connection = getattr(self._local, "connection", None)
        if connection is None or self._local.owner != owner:
            raise ActionRejected("RUN_TRANSACTION_REQUIRED")
        return connection

    def setup(self):
        with self._transaction(None):
            for statement in (*DDL, *ATTENTION_DDL):
                self._local.connection.execute(statement)

    @contextmanager
    def run_scope(self, owner, run_id):
        with self._transaction(owner):
            self.get_run(owner, run_id, for_update=True)
            yield

    @contextmanager
    def control_scope(self, owner, control_id):
        with self._transaction(owner):
            self._connection(owner).execute("SELECT pg_advisory_xact_lock(%s)",
                                           (lock_key(owner, control_id, "run-control"),))
            yield

    def get_run(self, owner, run_id, *, for_update=False):
        row = self._connection(owner).execute(
            "SELECT document FROM runtime_runs WHERE user_id=%s AND environment=%s AND run_id=%s"
            + (" FOR UPDATE" if for_update else ""), (owner.user_id, owner.environment, run_id),
        ).fetchone()
        if row is None:
            return None
        run = decode_record(row["document"], RunRecord)
        if run.owner != owner or run.run_id != run_id:
            raise ActionRejected("INVALID_RUN_RECORD")
        return run

    def restart_identity(self, owner, run_id):
        # NEVER SELECT/decode the document or old initial inputs/versions.
        row = self._connection(owner).execute(
            """SELECT user_id, environment, run_id,
                      document->>'status' AS status,
                      document->>'definition_key' AS definition_key
                 FROM runtime_runs
                WHERE user_id=%s AND environment=%s AND run_id=%s""",
            (owner.user_id, owner.environment, run_id),
        ).fetchone()
        if row is None:
            return None
        if (row["user_id"] != owner.user_id or row["environment"] != owner.environment
                or row["run_id"] != run_id
                or row["status"] not in {"RUNNING", "STOPPED", "SUCCEEDED", "FAILED"}
                or type(row["definition_key"]) is not str or not row["definition_key"]):
            raise ActionRejected("INVALID_RESTART_IDENTITY")
        return {"runId": run_id, "status": row["status"], "definitionKey": row["definition_key"]}

    def put_run(self, run):
        row = self._connection(run.owner).execute(
            """INSERT INTO runtime_runs (user_id,environment,run_id,thread_id,document)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (user_id,environment,run_id) DO UPDATE SET document=EXCLUDED.document
               WHERE runtime_runs.thread_id=EXCLUDED.thread_id
                 AND (runtime_runs.document->>'status'='RUNNING'
                      OR EXCLUDED.document->>'status'=runtime_runs.document->>'status')
               RETURNING run_id""",
            (run.owner.user_id, run.owner.environment, run.run_id, run.thread_id, Jsonb(encode_record(run))),
        ).fetchone()
        if row is None:
            raise ActionRejected("RUN_TERMINAL_CONFLICT")

    def get_control(self, owner, control_id):
        row = self._connection(owner).execute(
            "SELECT document FROM runtime_run_controls WHERE user_id=%s AND environment=%s AND control_id=%s",
            (owner.user_id, owner.environment, control_id),
        ).fetchone()
        if row is None:
            return None
        control = decode_record(row["document"], RunControl)
        if control.control_id != control_id:
            raise ActionRejected("INVALID_RUN_RECORD")
        return control

    def put_control(self, owner, control):
        old = self.get_control(owner, control.control_id)
        if old is not None and (old.payload_json != control.payload_json or old.run_id != control.run_id):
            raise ActionRejected("CONTROL_REQUEST_CONFLICT")
        self._connection(owner).execute(
            """INSERT INTO runtime_run_controls (user_id,environment,control_id,document)
               VALUES (%s,%s,%s,%s) ON CONFLICT (user_id,environment,control_id)
               DO UPDATE SET document=EXCLUDED.document""",
            (owner.user_id, owner.environment, control.control_id, Jsonb(encode_record(control))),
        )

    def get_operation(self, owner, run_id, operation_id):
        row = self._connection(owner).execute(
            """SELECT document FROM runtime_operation_facts
               WHERE user_id=%s AND environment=%s AND run_id=%s AND operation_id=%s""",
            (owner.user_id, owner.environment, run_id, operation_id),
        ).fetchone()
        if row is None:
            return None
        fact = decode_record(row["document"], OperationFact)
        if fact.operation_id != operation_id:
            raise ActionRejected("INVALID_RUN_RECORD")
        return fact

    def put_operation(self, owner, run_id, fact):
        self._connection(owner).execute(
            """INSERT INTO runtime_operation_facts (user_id,environment,run_id,operation_id,document)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT (user_id,environment,run_id,operation_id)
               DO UPDATE SET document=EXCLUDED.document
               WHERE runtime_operation_facts.document->>'status'='IN_FLIGHT'""",
            (owner.user_id, owner.environment, run_id, fact.operation_id, Jsonb(encode_record(fact))),
        )

    def operations(self, owner, run_id):
        rows = self._connection(owner).execute(
            """SELECT document FROM runtime_operation_facts
               WHERE user_id=%s AND environment=%s AND run_id=%s ORDER BY operation_id""",
            (owner.user_id, owner.environment, run_id),
        ).fetchall()
        return tuple(decode_record(row["document"], OperationFact) for row in rows)
