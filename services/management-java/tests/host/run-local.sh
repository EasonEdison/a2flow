#!/usr/bin/env bash
set -euo pipefail
: "${PG_BIN:?Set PG_BIN to local PostgreSQL binaries directory}"
: "${JAVA_HOME:?Set JAVA_HOME to a JDK 17 installation}"
export PATH="$JAVA_HOME/bin:$PATH"
java -version 2>&1 | head -1 | grep -q '"17\.' || { printf '本脚本要求JDK17\n'; exit 1; }
project_dir="$(cd "$(dirname "$0")/../.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/a2flow-host-pg.XXXXXX")"
host_pid=""
cleanup() {
  if [[ -n "$host_pid" ]]; then kill "$host_pid" 2>/dev/null || true; wait "$host_pid" 2>/dev/null || true; fi
  "$PG_BIN/pg_ctl" -D "$test_dir/data" -m fast stop >/dev/null 2>&1 || true
  printf '隔离服务已停止，证据保留：%s\n' "$test_dir"
}
trap cleanup EXIT
cd "$project_dir"
for port in 56478 18790 18791 18792 18793; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    printf '测试端口已占用，拒绝连接现有服务：%s\n' "$port"; exit 1
  fi
done
build_dir="$test_dir/build"
if ! mvn -q -DskipTests -Dmanagement.build.directory="$build_dir" test-compile dependency:build-classpath -Dmdep.outputFile="$test_dir/classpath.txt" > "$test_dir/build.log" 2>&1; then
  head -25 "$test_dir/build.log"; printf '完整构建日志：%s/build.log\n' "$test_dir"; exit 1
fi
test -f frontend/dist/index.html || { printf '先在frontend运行npm run build\n'; exit 1; }
"$PG_BIN/initdb" -D "$test_dir/data" -A trust --no-locale -E UTF8 > "$test_dir/initdb.log"
"$PG_BIN/pg_ctl" -D "$test_dir/data" -l "$test_dir/postgres.log" -o "-h 127.0.0.1 -p 56478 -k $test_dir" start
"$PG_BIN/createdb" -h 127.0.0.1 -p 56478 management_host_test
export A2FLOW_MANAGEMENT_JDBC_URL=jdbc:postgresql://127.0.0.1:56478/management_host_test
export A2FLOW_MANAGEMENT_DB_USER="$(id -un)"
export A2FLOW_MANAGEMENT_DB_PASSWORD=synthetic-isolated-db-only
export A2FLOW_MANAGEMENT_CONFIG="$project_dir/tests/host/management.json"
export A2FLOW_MANAGEMENT_NAMESPACE=host-smoke
export A2FLOW_MANAGEMENT_BROWSER_ORIGINS=http://127.0.0.1:18790
export A2FLOW_MANAGEMENT_PORT=18790
export A2FLOW_ACCOUNT_LOGIN_ORIGIN=http://127.0.0.1:18791
export A2FLOW_PUBLICATION_BRIDGE_URL=http://127.0.0.1:18792
export A2FLOW_PUBLICATION_BRIDGE_TOKEN=synthetic-publication-test-token-not-live
export A2FLOW_MANAGEMENT_STATIC_DIR="$project_dir/frontend/dist"
export A2FLOW_RUNTIME_RPC_MODE=LOOPBACK
export A2FLOW_RUNTIME_RPC_PORT=18793
export A2FLOW_CAPABILITY_GRPC_TARGETS_JSON='{}'
classpath="$build_dir/classes:$build_dir/test-classes:$(<"$test_dir/classpath.txt")"
java -cp "$classpath" dev.a2flow.management.storage.db.migration.ExplicitManagementMigration --apply-new-instance
java -cp "$classpath" dev.a2flow.management.host.ManagementApplication > "$test_dir/host.log" 2>&1 &
host_pid=$!
for ((attempt=0; attempt<100; attempt++)); do
  if curl --fail --silent --max-time 1 http://127.0.0.1:18790/management >/dev/null; then break; fi
  if ! kill -0 "$host_pid" 2>/dev/null; then printf '启动失败，查看 %s/host.log\n' "$test_dir"; exit 1; fi
  sleep 0.2
done
PSQL="$PG_BIN/psql" node tests/host/http-smoke.mjs | tee "$test_dir/test.log"
java -cp "$classpath" dev.a2flow.management.capabilityrpc.RuntimeGrpcHostProbe 18793 | tee "$test_dir/rpc-test.log"
