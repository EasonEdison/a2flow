#!/usr/bin/env bash
set -euo pipefail
: "${PG_BIN:?PostgreSQL bin directory required}"
: "${PYTHON_SOURCE:?Exact existing Python source checkout required}"
: "${PYTHON_BIN:?Python with psycopg and existing public package dependencies required}"
test_port="${PG_TEST_PORT:-56476}"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/a2flow-publication-pg.XXXXXX")"
bridge_dir="$(cd "$(dirname "$0")" && pwd)"
cleanup() {
  "$PG_BIN/pg_ctl" -D "$test_dir/data" -m fast stop >/dev/null 2>&1 || true
  printf 'Temporary cluster stopped; evidence: %s\n' "$test_dir"
}
trap cleanup EXIT
"$PG_BIN/initdb" -D "$test_dir/data" -A trust --no-locale -E UTF8 > "$test_dir/initdb.log"
"$PG_BIN/pg_ctl" -D "$test_dir/data" -l "$test_dir/postgres.log" -o "-h 127.0.0.1 -p $test_port -k $test_dir" start
"$PG_BIN/createdb" -h 127.0.0.1 -p "$test_port" publication_prt
"$PG_BIN/createdb" -h 127.0.0.1 -p "$test_port" publication_online
export PYTHONPATH="$PYTHON_SOURCE:$PYTHON_SOURCE/packages/contracts/src:$PYTHON_SOURCE/packages/asset-store/src:$PYTHON_SOURCE/services/skill-registry/src:$PYTHON_SOURCE/services/capability-registry/src:$PYTHON_SOURCE/services/a2ui-composer/src:$PYTHON_SOURCE/services/management-api/src:$PYTHON_SOURCE/examples/activity-planning"
"$PYTHON_BIN" "$bridge_dir/test_publication.py" "$test_port" 2>&1 | tee "$test_dir/test.log"
