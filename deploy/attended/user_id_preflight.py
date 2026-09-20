"""Read-only userId column inventory. Never casts, assigns or logs raw identities.

Use A2FLOW_USER_ID_AUDIT_DSN for an explicitly selected database. Column checks
alone cannot approve serialized checkpoints, queues, gray lists or Store keys.
"""

import json
import os

import psycopg
from psycopg import sql
from skillweave_contracts.user_id import user_id_from_wire


def audit(connection):
    result = []
    columns = connection.execute(
        "SELECT table_schema,table_name,column_name,data_type "
        "FROM information_schema.columns "
        "WHERE table_schema='public' AND column_name='user_id' "
        "ORDER BY table_name"
    ).fetchall()
    for schema, table, column, data_type in columns:
        counts = {"rows": 0, "invalid": 0, "null": 0}
        with connection.cursor(name="user_id_audit") as cursor:
            cursor.execute(sql.SQL("SELECT {} FROM {}.{}").format(
                sql.Identifier(column), sql.Identifier(schema), sql.Identifier(table),
            ))
            for (value,) in cursor:
                counts["rows"] += 1
                if value is None:
                    counts["null"] += 1
                else:
                    try:
                        user_id_from_wire(value)
                    except ValueError:
                        counts["invalid"] += 1
        result.append({"table": table, "column": column, "type": data_type, **counts})
    return {
        "columns": result,
        "columnValuesConvertible": bool(result) and all(
            not row["invalid"] and not row["null"] for row in result),
        "readyForDeployment": False,
        "remainingReview": [
            "serialized runtime/checkpoint ownership",
            "queue payloads and asset gray user lists",
            "memory namespaces and legacy identity mapping",
            "foreign keys, unique keys, application contracts and deployment ordering",
        ],
    }


def main():
    dsn = os.environ.get("A2FLOW_USER_ID_AUDIT_DSN")
    if not dsn:
        raise SystemExit("A2FLOW_USER_ID_AUDIT_DSN_REQUIRED")
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '30s'")
        report = audit(connection)
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["columnValuesConvertible"] else 2)


if __name__ == "__main__":
    main()
