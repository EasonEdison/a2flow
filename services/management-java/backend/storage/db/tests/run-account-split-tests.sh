#!/usr/bin/env bash
set -euo pipefail
umask 077
: "${PG_BIN:?Local PostgreSQL binaries required}"
: "${JAVA_HOME:?JDK17 required}"
export PATH="$JAVA_HOME/bin:$PATH"
test_port="${PG_TEST_PORT:-56508}"
unix_only="${A2FLOW_TEST_UNIX_SOCKET:-0}"
if [[ "$unix_only" != 1 ]] && lsof -nP -iTCP:"$test_port" -sTCP:LISTEN >/dev/null 2>&1; then
  printf 'Refusing occupied test port\n'; exit 1
fi
project_dir="$(cd "$(dirname "$0")/../../../.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/a2flow-account-split.XXXXXX")"
cleanup() {
  "$PG_BIN/pg_ctl" -D "$test_dir/data" -m fast stop >/dev/null 2>&1 || true
  printf '测试进程已停止，证据保留：%s\n' "$test_dir"
}
trap cleanup EXIT
cd "$project_dir"
mvn -q -DskipTests -Dmanagement.build.directory="$test_dir/build" test-compile dependency:build-classpath \
  -Dmdep.outputFile="$test_dir/classpath.txt" > "$test_dir/build.log" 2>&1
"$PG_BIN/initdb" -D "$test_dir/data" -A trust --no-locale -E UTF8 > "$test_dir/initdb.log"
database_host=127.0.0.1
if [[ "$unix_only" == 1 ]]; then
  database_host="$test_dir"
  "$PG_BIN/pg_ctl" -D "$test_dir/data" -l "$test_dir/postgres.log" -o "-c listen_addresses= -p $test_port -k $test_dir" start
  if lsof -nP -a -p "$(head -n 1 "$test_dir/data/postmaster.pid")" -iTCP -sTCP:LISTEN; then
    printf 'Unexpected PostgreSQL TCP listener\n'; exit 1
  fi
  socket_path="$(node -e 'process.stdout.write(encodeURIComponent(process.argv[1]))' "$test_dir/.s.PGSQL.$test_port")"
  jdbc_root=jdbc:postgresql://localhost
  jdbc_query="?socketFactory=org.newsclub.net.unix.AFUNIXSocketFactory%24FactoryArg&socketFactoryArg=$socket_path&sslmode=disable"
else
  "$PG_BIN/pg_ctl" -D "$test_dir/data" -l "$test_dir/postgres.log" -o "-h 127.0.0.1 -p $test_port -k $test_dir" start
  jdbc_root="jdbc:postgresql://127.0.0.1:$test_port"
  jdbc_query=""
fi
for database in account_split_management account_split_auth; do
  "$PG_BIN/createdb" -h "$database_host" -p "$test_port" "$database"
done
java -cp "$test_dir/build/classes:$test_dir/build/test-classes:$(<"$test_dir/classpath.txt")" \
  dev.a2flow.management.storage.db.AccountSessionDataSourceJdbcTest \
  "$jdbc_root/account_split_management$jdbc_query" \
  "$jdbc_root/account_split_auth$jdbc_query" "$(id -un)" 2>&1 | tee "$test_dir/test.log"
