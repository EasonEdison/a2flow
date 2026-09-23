#!/usr/bin/env bash
set -euo pipefail
: "${PG_BIN:?Set PG_BIN to local PostgreSQL binaries}"
project_dir="$(cd "$(dirname "$0")/../../../.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/a2flow-rpc-pg.XXXXXX")"
test_port="${PG_TEST_PORT:-56478}"
build_dir="${RPC_BUILD_DIR:-$test_dir/build}"
cleanup() {
  "$PG_BIN/pg_ctl" -D "$test_dir/data" -m fast stop >/dev/null 2>&1 || true
  printf '隔离PG已停止，RPC探针证据保留：%s\n' "$test_dir"
}
trap cleanup EXIT
cd "$project_dir"
mvn -q -DskipTests -Dmanagement.build.directory="$build_dir" test-compile dependency:build-classpath -Dmdep.outputFile="$build_dir/classpath.txt"
"$PG_BIN/initdb" -D "$test_dir/data" -A trust --no-locale -E UTF8 > "$test_dir/initdb.log"
"$PG_BIN/pg_ctl" -D "$test_dir/data" -l "$test_dir/postgres.log" -o "-h 127.0.0.1 -p $test_port -k $test_dir" start
"$PG_BIN/createdb" -h 127.0.0.1 -p "$test_port" capability_rpc_test
java -cp "$build_dir/classes:$build_dir/test-classes:$(<"$build_dir/classpath.txt")" \
  dev.a2flow.management.capabilityrpc.CapabilityGrpcJdbcProbe \
  "jdbc:postgresql://127.0.0.1:$test_port/capability_rpc_test" "$(id -un)" | tee "$test_dir/probe.log"
