#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${PG_BIN:?Local PostgreSQL binaries required}"
: "${JAVA_HOME:?JDK17 required}"
: "${PYTHON_SOURCE:?Exact isolated Python source required}"
: "${PYTHON_BIN:?Python environment with psycopg and runtime dependencies required}"
export PATH="$JAVA_HOME/bin:$PATH"
project_dir="$(cd "$(dirname "$0")/../.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/a2flow-chat-integration.XXXXXX")"
host_pid=""; bridge_pid=""; business_pid=""
cleanup() {
  for process in "$host_pid" "$bridge_pid" "$business_pid"; do
    if [[ -n "$process" ]]; then kill "$process" 2>/dev/null || true; wait "$process" 2>/dev/null || true; fi
  done
  "$PG_BIN/pg_ctl" -D "$test_dir/data" -m fast stop >/dev/null 2>&1 || true
  printf '联调环境已停止，证据保留：%s\n' "$test_dir"
}
trap cleanup EXIT
trap 'exit 0' TERM INT
cd "$project_dir"
for port in 56502 18890 18891 18892 18893 18894; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    printf '拒绝连接已有监听端口：%s\n' "$port"; exit 1
  fi
done
printf '%s\n' "$$" > "$test_dir/launcher.pid"
printf '创建隔离联调目录：%s\n' "$test_dir"
build_dir="$test_dir/build"
if ! mvn -q -DskipTests -Dmanagement.build.directory="$build_dir" test-compile dependency:build-classpath \
    -Dmdep.outputFile="$test_dir/classpath.txt" > "$test_dir/build.log" 2>&1; then
  printf '构建失败，查看 %s/build.log\n' "$test_dir"; exit 1
fi
classpath="$build_dir/classes:$build_dir/test-classes:$(<"$test_dir/classpath.txt")"
mkdir "$test_dir/fixture-classes"
javac -cp "$classpath" -d "$test_dir/fixture-classes" tests/runtime/SyntheticBusinessGrpc.java
"$PG_BIN/initdb" -D "$test_dir/data" -A trust --no-locale -E UTF8 > "$test_dir/initdb.log"
"$PG_BIN/pg_ctl" -D "$test_dir/data" -l "$test_dir/postgres.log" -o "-h 127.0.0.1 -p 56502 -k $test_dir" start
for database in chat_rpc_management chat_rpc_prt chat_rpc_online; do
  "$PG_BIN/createdb" -h 127.0.0.1 -p 56502 "$database"
done
export INTEGRATION_JAVA_ROOT="$project_dir"
export PYTHONPATH="$project_dir/publication-bridge:$PYTHON_SOURCE:$PYTHON_SOURCE/packages/contracts/src:$PYTHON_SOURCE/packages/asset-store/src:$PYTHON_SOURCE/services/skill-registry/src:$PYTHON_SOURCE/services/capability-registry/src:$PYTHON_SOURCE/services/a2ui-composer/src:$PYTHON_SOURCE/services/management-api/src:$PYTHON_SOURCE/examples/activity-planning:$PYTHON_SOURCE/apps/agent-runtime/src"
export A2FLOW_MANAGEMENT_JDBC_URL=jdbc:postgresql://127.0.0.1:56502/chat_rpc_management
export A2FLOW_MANAGEMENT_DB_USER="$(id -un)"
export A2FLOW_MANAGEMENT_DB_PASSWORD=synthetic-isolated-db-only
java -cp "$classpath" dev.a2flow.management.storage.db.migration.ExplicitManagementMigration --apply-new-instance > "$test_dir/migration.log"
"$PYTHON_BIN" tests/runtime/prepare-integration.py "$test_dir"
source "$test_dir/environment.sh"
export A2FLOW_MANAGEMENT_CONFIG="$project_dir/tests/runtime/management.json"
export A2FLOW_MANAGEMENT_BROWSER_ORIGINS=http://127.0.0.1:18890
export A2FLOW_MANAGEMENT_PORT=18890
# Login proxy is not used: the synthetic session exists in the isolated existing-account schema fixture.
export A2FLOW_ACCOUNT_LOGIN_ORIGIN=http://127.0.0.1:18891
export A2FLOW_MANAGEMENT_STATIC_DIR="$project_dir/frontend/dist"
export A2FLOW_RUNTIME_RPC_MODE=LOOPBACK
export A2FLOW_RUNTIME_RPC_PORT=18893
export A2FLOW_CAPABILITY_GRPC_TARGETS_JSON='{"integration-business":{"PRT":{"host":"127.0.0.1","port":18894,"loopbackPlaintext":true},"ONLINE":{"host":"127.0.0.1","port":18894,"loopbackPlaintext":true}}}'
export M_FRESH_TEST_DB=1
export B_WEB_DIR="$PYTHON_SOURCE/apps/digital-employee/web"
"$PYTHON_BIN" publication-bridge/bridge.py > "$test_dir/bridge.log" 2>&1 & bridge_pid=$!
java -cp "$test_dir/fixture-classes:$classpath" dev.a2flow.management.capabilityrpc.SyntheticBusinessGrpc 18894 "$RPC_DESCRIPTOR_FILE" > "$test_dir/business.log" 2>&1 & business_pid=$!
java -cp "$classpath" dev.a2flow.management.host.ManagementApplication > "$test_dir/host.log" 2>&1 & host_pid=$!
services_ready=false
for ((attempt=0; attempt<150; attempt++)); do
  if ! kill -0 "$host_pid" "$bridge_pid" "$business_pid" 2>/dev/null; then printf '进程启动失败，请查看隔离目录日志\n'; exit 1; fi
  if [[ -s "$RPC_DESCRIPTOR_FILE" ]] && curl --fail --silent --max-time 1 http://127.0.0.1:18890/management >/dev/null \
      && lsof -nP -iTCP:18892 -sTCP:LISTEN >/dev/null 2>&1 && lsof -nP -iTCP:18893 -sTCP:LISTEN >/dev/null 2>&1; then services_ready=true; break; fi
  sleep 0.2
done
if [[ "$services_ready" != true ]]; then printf '服务就绪超时，拒绝进入作者态验收\n'; exit 1; fi
printf '服务已启动；私有环境文件：%s/environment.sh\n' "$test_dir"
printf '等待M作者态脚本文件就绪：tests/runtime/m-authoring-rpc.mjs\n'
while [[ ! -f tests/runtime/m-authoring-rpc.mjs && ! -f "$test_dir/STOP" ]]; do sleep 1; done
if [[ ! -f "$test_dir/STOP" ]]; then
  if node tests/runtime/m-authoring-rpc.mjs > "$test_dir/m-authoring.log" 2>&1; then
    "$PYTHON_BIN" - "$test_dir" <<'PY'
import json, pathlib, sys
directory = pathlib.Path(sys.argv[1])
runtime = json.loads((directory / "runtime-env.json").read_text())
runtime.update(json.loads((directory / "authored-assets.json").read_text()))
(directory / "runtime-env.json").write_text(json.dumps(runtime, ensure_ascii=False, indent=2))
(directory / "runtime-env.json").chmod(0o600)
PY
    printf 'M作者态完成；Python验收环境：%s/runtime-env.json\n' "$test_dir"
  else
    printf 'M作者态未完成；环境保留便于诊断，查看 %s/m-authoring.log\n' "$test_dir"
  fi
fi
printf '保持环境运行；root验收后创建 %s/STOP 或向launcher.pid对应进程发送TERM。\n' "$test_dir"
while [[ ! -f "$test_dir/STOP" ]]; do sleep 1; done
