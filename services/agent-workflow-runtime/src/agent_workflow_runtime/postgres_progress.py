"""Committed PostgreSQL display records. No execution/control locks or replay."""

from contextlib import contextmanager
from hashlib import sha256
import re

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import ActionRejected
from .postgres_projection import PostgresProjection
from .progress_writer import MAX_FRAME_BYTES, MAX_RECORDS, encoded, validate_record
from .service import identifier, require_owner


DDL = (
    """CREATE TABLE IF NOT EXISTS runtime_capture_heads (
        user_id TEXT NOT NULL, environment TEXT NOT NULL, run_id TEXT NOT NULL,
        node_id TEXT NOT NULL, execution_id TEXT NOT NULL,
        catalog_seq BIGINT NOT NULL DEFAULT 0, last_seq BIGINT NOT NULL DEFAULT 0,
        node_operation_id TEXT, sealed BOOLEAN NOT NULL DEFAULT FALSE,
        incomplete BOOLEAN NOT NULL DEFAULT FALSE, observation_outcome TEXT,
        last_batch_id TEXT, last_batch_digest TEXT,
        PRIMARY KEY(user_id, environment, run_id, node_id, execution_id),
        FOREIGN KEY(user_id, environment, run_id) REFERENCES runtime_runs,
        CHECK(last_seq >= 0), CHECK(catalog_seq >= 0))""",
    """CREATE INDEX IF NOT EXISTS runtime_capture_catalog_idx
        ON runtime_capture_heads(user_id, environment, run_id, catalog_seq)
        WHERE execution_id <> ''""",
    """CREATE TABLE IF NOT EXISTS runtime_display_records (
        user_id TEXT NOT NULL, environment TEXT NOT NULL, run_id TEXT NOT NULL,
        node_id TEXT NOT NULL, execution_id TEXT NOT NULL, seq BIGINT NOT NULL,
        batch_id TEXT NOT NULL, batch_digest TEXT NOT NULL, batch_index INTEGER NOT NULL,
        document JSONB NOT NULL,
        PRIMARY KEY(user_id, environment, run_id, node_id, execution_id, seq),
        UNIQUE(user_id, environment, run_id, node_id, execution_id, batch_id, batch_index),
        FOREIGN KEY(user_id, environment, run_id, node_id, execution_id)
            REFERENCES runtime_capture_heads,
        CHECK(seq > 0 AND seq <= 2000))""",
)


def execution_id(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{32}", value) is None:
        raise ActionRejected("INVALID_EXECUTION_ID")
    return value


def cursor(value, namespace):
    if value is None:
        return 0
    if type(value) is not str or not value.startswith(namespace + ":"):
        raise ActionRejected("INVALID_PROGRESS_CURSOR")
    number = value[len(namespace) + 1:]
    if not re.fullmatch("0|[1-9][0-9]{0,18}", number):
        raise ActionRejected("INVALID_PROGRESS_CURSOR")
    return int(number)


def page_limit(value):
    if type(value) is not int or not 1 <= value <= 100:
        raise ActionRejected("INVALID_PROGRESS_LIMIT")
    return value


class PostgresProgress(PostgresProjection):
    @contextmanager
    def _write(self):
        connection = self._connect(
            self._conninfo, autocommit=True, row_factory=dict_row, connect_timeout=1,
            options="-c statement_timeout=750 -c lock_timeout=250",
            application_name="a2flow-runtime07-write",
        )
        try:
            with connection.transaction():
                yield connection
        finally:
            connection.close()

    def setup(self):
        # Host-controlled schema setup; never called by reader/callback/subscriber.
        with self._write() as connection:
            for statement in DDL:
                connection.execute(statement)

    @staticmethod
    def _binding(binding):
        return (binding["userId"], binding["environment"], identifier(binding["runId"]),
                identifier(binding["nodeId"]), execution_id(binding["executionId"]))

    @staticmethod
    def _head(connection, key):
        return connection.execute(
            """SELECT catalog_seq,last_seq,sealed,incomplete,observation_outcome,last_batch_id,last_batch_digest
               FROM runtime_capture_heads
               WHERE user_id=%s AND environment=%s AND run_id=%s
                 AND node_id=%s AND execution_id=%s FOR UPDATE""", key,
        ).fetchone()

    def append(self, binding, batch_id, records, *, seal=None, incomplete=False):
        key = self._binding(binding)
        if len(records) > 64 or any(len(encoded(record)) > MAX_FRAME_BYTES for record in records):
            raise ActionRejected("INVALID_PROGRESS_BATCH")
        for record in records:
            validate_record(record)
        digest = sha256(encoded({"records": records, "seal": seal, "incomplete": incomplete})).hexdigest()
        with self._write() as connection:
            head = self._head(connection, key)
            if head is None:
                # A private catalog head uses empty node/execution; it cannot be
                # addressed by the public identifier validators. Its lock orders
                # head creation/commit without touching runtime_runs admission.
                catalog = (*key[:3], "", "")
                connection.execute(
                    """INSERT INTO runtime_capture_heads(user_id,environment,run_id,node_id,execution_id)
                       VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", catalog)
                self._head(connection, catalog)
                head = self._head(connection, key)
                if head is None:
                    row = connection.execute(
                        """UPDATE runtime_capture_heads SET last_seq=last_seq+1
                           WHERE user_id=%s AND environment=%s AND run_id=%s
                             AND node_id=%s AND execution_id=%s RETURNING last_seq""", catalog,
                    ).fetchone()
                    connection.execute(
                        """INSERT INTO runtime_capture_heads
                           (user_id,environment,run_id,node_id,execution_id,catalog_seq,node_operation_id)
                           VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                        (*key, row["last_seq"], binding.get("nodeOperationId")))
                    head = self._head(connection, key)
            if head.get("last_batch_id") == batch_id:
                if head.get("last_batch_digest") != digest:
                    raise ActionRejected("PROGRESS_BATCH_IDENTITY_CONFLICT")
                return
            previous = connection.execute(
                """SELECT batch_digest,count(*) AS count FROM runtime_display_records
                   WHERE user_id=%s AND environment=%s AND run_id=%s AND node_id=%s
                     AND execution_id=%s AND batch_id=%s GROUP BY batch_digest""",
                (*key, batch_id),
            ).fetchall()
            if previous:
                if len(previous) != 1 or previous[0]["batch_digest"] != digest or previous[0]["count"] != len(records):
                    raise ActionRejected("PROGRESS_BATCH_IDENTITY_CONFLICT")
                return
            if head["sealed"] or head["observation_outcome"] == "UNAVAILABLE":
                raise ActionRejected("PROGRESS_CAPTURE_CLOSED")
            last = head["last_seq"]
            if last + len(records) > MAX_RECORDS:
                raise ActionRejected("PROGRESS_RECORD_LIMIT")
            if records:
                params, values = [], []
                for index, record in enumerate(records):
                    values.append("(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)")
                    params.extend((*key, last + index + 1, batch_id, digest, index, Jsonb(record)))
                connection.execute(
                    """INSERT INTO runtime_display_records
                       (user_id,environment,run_id,node_id,execution_id,seq,batch_id,batch_digest,batch_index,document)
                       VALUES """ + ",".join(values), params)
            connection.execute(
                """UPDATE runtime_capture_heads SET last_seq=%s,sealed=%s,
                       incomplete=%s,observation_outcome=%s,last_batch_id=%s,last_batch_digest=%s
                   WHERE user_id=%s AND environment=%s AND run_id=%s AND node_id=%s AND execution_id=%s""",
                (last + len(records), seal is not None, bool(incomplete or head["incomplete"]),
                 seal, batch_id, digest, *key))

    def unavailable(self, binding):
        with self._write() as connection:
            connection.execute(
                """UPDATE runtime_capture_heads SET incomplete=TRUE,observation_outcome=\'UNAVAILABLE\'
                   WHERE user_id=%s AND environment=%s AND run_id=%s AND node_id=%s AND execution_id=%s""",
                self._binding(binding))

    @staticmethod
    def _run_exists(connection, key):
        if connection.execute(
            "SELECT run_id FROM runtime_runs WHERE user_id=%s AND environment=%s AND run_id=%s", key,
        ).fetchone() is None:
            raise ActionRejected("RUN_NOT_FOUND")

    def catalog(self, owner, run_id, *, after=None, limit=100):
        require_owner(owner)
        key, limit = self._key(owner, run_id), page_limit(limit)
        position = cursor(after, run_id)
        with self._read(owner) as connection:
            self._run_exists(connection, key)
            row = connection.execute(
                """SELECT last_seq FROM runtime_capture_heads WHERE user_id=%s AND environment=%s
                   AND run_id=%s AND node_id='' AND execution_id=''""", key,
            ).fetchone()
            maximum = row["last_seq"] if row else 0
            if position > maximum:
                raise ActionRejected("FUTURE_PROGRESS_CURSOR")
            rows = connection.execute(
                """SELECT node_id,execution_id,node_operation_id,catalog_seq,last_seq,sealed,incomplete,observation_outcome
                   FROM runtime_capture_heads WHERE user_id=%s AND environment=%s AND run_id=%s
                     AND execution_id<>'' AND catalog_seq>%s ORDER BY catalog_seq LIMIT %s""",
                (*key, position, limit),
            ).fetchall()
        last = rows[-1]["catalog_seq"] if rows else position
        return {"runId": run_id, "segments": rows, "nextCursor": f"{run_id}:{last}",
                "hasMore": last < maximum, "capture": "UNCONFIRMED" if not rows else "RECORDED"}

    def history(self, owner, run_id, node_id, segment_id, *, after=None, limit=100):
        require_owner(owner)
        key = (*self._key(owner, run_id), identifier(node_id), execution_id(segment_id))
        position, limit = cursor(after, segment_id), page_limit(limit)
        with self._read(owner) as connection:
            self._run_exists(connection, key[:3])
            head = connection.execute(
                """SELECT last_seq,sealed,incomplete,observation_outcome FROM runtime_capture_heads
                   WHERE user_id=%s AND environment=%s AND run_id=%s AND node_id=%s AND execution_id=%s""", key,
            ).fetchone()
            if head is None:
                raise ActionRejected("PROGRESS_NOT_FOUND")
            if position > head["last_seq"]:
                raise ActionRejected("FUTURE_PROGRESS_CURSOR")
            rows = connection.execute(
                """SELECT seq,document FROM runtime_display_records
                   WHERE user_id=%s AND environment=%s AND run_id=%s AND node_id=%s
                     AND execution_id=%s AND seq>%s ORDER BY seq LIMIT %s""",
                (*key, position, limit),
            ).fetchall()
        if not rows and position < head["last_seq"]:
            raise ActionRejected("PROGRESS_INTEGRITY_ERROR")
        records, size, last = [], 2048, position
        for row in rows:
            try:
                record = {"seq": row["seq"], **validate_record(row["document"])}
            except (ValueError, TypeError, KeyError):
                raise ActionRejected("PROGRESS_INTEGRITY_ERROR") from None
            length = len(encoded(record))
            if (length > MAX_FRAME_BYTES + 128 or row["seq"] != last + 1
                    or row["seq"] > head["last_seq"]):
                raise ActionRejected("PROGRESS_INTEGRITY_ERROR")
            if size + length > 256 * 1024:
                break
            records.append(record)
            size += length
            last = row["seq"]
        return {"runId": run_id, "nodeId": node_id, "executionId": segment_id,
                "capture": head, "records": records, "nextCursor": f"{segment_id}:{last}",
                "hasMore": last < head["last_seq"],
                "statusReference": {"runId": run_id, "nodeId": node_id}}
