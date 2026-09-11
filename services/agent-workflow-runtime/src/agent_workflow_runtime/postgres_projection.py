"""Independent read-only committed projections; no AF03 or execution locks."""

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .models import ActionRejected
from .projections import COLLECTION_LIMIT, receipt, snapshot
from .service import identifier, require_owner


class PostgresProjection:
    def __init__(self, conninfo, *, connection_factory=psycopg.connect):
        self._conninfo, self._connect = conninfo, connection_factory

    @contextmanager
    def _read(self, owner):
        require_owner(owner)
        connection = None
        try:
            connection = self._connect(
                self._conninfo, autocommit=True, row_factory=dict_row,
                connect_timeout=2,
                options="-c statement_timeout=1500 -c lock_timeout=500",
                application_name="a2flow-runtime05-read",
            )
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                yield connection
        except ActionRejected:
            raise
        except Exception:
            raise ActionRejected("PROJECTION_UNAVAILABLE") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _key(owner, value):
        return owner.user_id, owner.environment, identifier(value)

    def control(self, owner, control_id):
        with self._read(owner) as connection:
            row = connection.execute(
                """SELECT document->>'run_id' AS run_id, document->>'status' AS status
                   FROM runtime_run_controls
                   WHERE user_id=%s AND environment=%s AND control_id=%s
                     AND document->>'schemaVersion'='1'""",
                self._key(owner, control_id),
            ).fetchone()
            return receipt(row, control_id)

    def restart_identity(self, owner, run_id):
        with self._read(owner) as connection:
            row = connection.execute(
                """SELECT run_id, document->>'status' AS status,
                          document->>'definition_key' AS definition_key
                   FROM runtime_runs
                   WHERE user_id=%s AND environment=%s AND run_id=%s
                     AND document->>'schemaVersion'='1'""",
                self._key(owner, run_id),
            ).fetchone()
            if row is None:
                raise ActionRejected("RUN_NOT_FOUND")
            if row["status"] != "STOPPED":
                raise ActionRejected("RESTART_SOURCE_OUTSIDE_THIS_SLICE")
            return {"runId": row["run_id"], "definitionKey": identifier(row["definition_key"])}

    def run(self, owner, run_id):
        with self._read(owner) as connection:
            key = self._key(owner, run_id)
            run = connection.execute(
                """SELECT r.run_id, r.document->>'status' AS status,
                          (r.document->>'revision')::bigint AS revision,
                          r.document->>'initial_control_id' AS initial_control_id,
                          c.document->>'status' AS initial_control_status
                   FROM runtime_runs AS r
                   LEFT JOIN runtime_run_controls AS c
                     ON c.user_id=r.user_id AND c.environment=r.environment
                       AND c.control_id=r.document->>'initial_control_id'
                   WHERE r.user_id=%s AND r.environment=%s AND r.run_id=%s
                     AND r.document->>'schemaVersion'='1'""", key,
            ).fetchone()
            if run is None:
                raise ActionRejected("RUN_NOT_FOUND")
            operations = connection.execute(
                """SELECT document->>'node_id' AS node_id, document->>'kind' AS kind,
                          document->>'status' AS status, count(*) AS count
                   FROM runtime_operation_facts
                   WHERE user_id=%s AND environment=%s AND run_id=%s
                   GROUP BY 1,2,3 ORDER BY 1,2,3 LIMIT %s""",
                (*key, COLLECTION_LIMIT + 1),
            ).fetchall()
            interactions = connection.execute(
                """SELECT node_id, interaction_id, document->>'phase' AS phase,
                          (document->>'run_active')::boolean AS run_active,
                          (document->>'node_waiting')::boolean AS node_waiting,
                          jsonb_array_length(document->'attempts') AS attempt_count,
                          document#>>'{attempts,-1,request,control_request_id}' AS control_id,
                          document#>>'{attempts,-1,status}' AS attempt_status,
                          (document#>>'{attempts,-1,business_success}')::boolean AS business_success,
                          (document#>>'{attempts,-1,interaction_completed}')::boolean AS interaction_completed,
                          document#>>'{attempts,-1,resume_status}' AS resume_status
                   FROM runtime_interactions
                   WHERE user_id=%s AND environment=%s AND run_id=%s
                   ORDER BY node_id, interaction_id LIMIT %s""",
                (*key, COLLECTION_LIMIT + 1),
            ).fetchall()
            return snapshot(run, operations, interactions)
