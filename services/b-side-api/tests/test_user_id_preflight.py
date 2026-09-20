import json
import os
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from deploy.attended.user_id_preflight import audit


@unittest.skipUnless(os.environ.get("A2FLOW_TEST_CHAT_DSN"), "disposable PG required")
class UserIdPreflightTests(unittest.TestCase):
    def test_counts_only_and_database_remains_unchanged(self):
        dsn = os.environ["A2FLOW_TEST_CHAT_DSN"]
        table = "identity_audit_" + uuid4().hex
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE TABLE {} (user_id text)").format(
                sql.Identifier(table)))
            for value in ("9223372036854775807", "01", "fixture-name", None):
                connection.execute(sql.SQL("INSERT INTO {} VALUES (%s)").format(
                    sql.Identifier(table)), (value,))
        with psycopg.connect(dsn) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            report = audit(connection)
            rows = connection.execute(sql.SQL("SELECT user_id FROM {}").format(
                sql.Identifier(table))).fetchall()
        result = next(row for row in report["columns"] if row["table"] == table)
        self.assertEqual((4, 2, 1), (result["rows"], result["invalid"], result["null"]))
        self.assertFalse(report["readyForDeployment"])
        self.assertFalse(report["columnValuesConvertible"])
        self.assertNotIn("fixture-name", json.dumps(report))
        self.assertEqual([("9223372036854775807",), ("01",), ("fixture-name",), (None,)], rows)
