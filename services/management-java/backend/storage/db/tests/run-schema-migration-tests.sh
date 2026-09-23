#!/usr/bin/env bash
set -euo pipefail
: "${PG_BIN:?Set PG_BIN to local PostgreSQL binaries directory}"
test_port="${PG_TEST_PORT:-56476}"
project_dir="$(cd "$(dirname "$0")/../../../.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/a2flow-schema-pg.XXXXXX")"
cleanup() {
  "$PG_BIN/pg_ctl" -D "$test_dir/data" -m fast stop >/dev/null 2>&1 || true
  printf '独立测试进程已停止，证据保留：%s\n' "$test_dir"
}
trap cleanup EXIT
cd "$project_dir"
mvn -q -DskipTests test-compile dependency:build-classpath -Dmdep.outputFile="$test_dir/classpath.txt"
"$PG_BIN/initdb" -D "$test_dir/data" -A trust --no-locale -E UTF8 > "$test_dir/initdb.log"
"$PG_BIN/pg_ctl" -D "$test_dir/data" -l "$test_dir/postgres.log" -o "-h 127.0.0.1 -p $test_port -k $test_dir" start
"$PG_BIN/createdb" -h 127.0.0.1 -p "$test_port" management_schema_test
java -cp "target/classes:target/test-classes:$(<"$test_dir/classpath.txt")" \
  dev.a2flow.management.storage.db.ManagementSchemaMigrationJdbcTest \
  "jdbc:postgresql://127.0.0.1:$test_port/management_schema_test" "$(id -un)" | tee "$test_dir/test.log"
