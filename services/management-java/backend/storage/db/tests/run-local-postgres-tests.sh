#!/usr/bin/env bash
set -euo pipefail

# Requires local PostgreSQL binaries and the listed public Maven dependencies in the local cache.
# Creates a new loopback-only cluster; never connects to an existing application database.
: "${PG_BIN:?Set PG_BIN to the directory containing initdb, pg_ctl, and createdb}"
test_port="${PG_TEST_PORT:-56474}"
maven_cache="${M2_REPOSITORY:-$HOME/.m2/repository}"
backend_dir="$(cd "$(dirname "$0")/../../.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/a2flow-workspace-pg.XXXXXX")"
test_classpath=""

dependencies=(
  com/fasterxml/jackson/core/jackson-databind/2.20.1/jackson-databind-2.20.1.jar
  com/fasterxml/jackson/core/jackson-core/2.20.1/jackson-core-2.20.1.jar
  com/fasterxml/jackson/core/jackson-annotations/2.20/jackson-annotations-2.20.jar
  org/postgresql/postgresql/42.7.7/postgresql-42.7.7.jar
  org/projectlombok/lombok/1.18.44/lombok-1.18.44.jar
  org/apache/commons/commons-lang3/3.20.0/commons-lang3-3.20.0.jar
  org/slf4j/slf4j-api/2.0.17/slf4j-api-2.0.17.jar
  com/google/guava/guava/33.5.0-jre/guava-33.5.0-jre.jar
  jakarta/annotation/jakarta.annotation-api/2.1.1/jakarta.annotation-api-2.1.1.jar
)
for artifact in core beans context aop expression jcl jdbc tx; do
  dependencies+=("org/springframework/spring-$artifact/6.2.5/spring-$artifact-6.2.5.jar")
done
for dependency in "${dependencies[@]}"; do
  test -f "$maven_cache/$dependency"
  test_classpath="${test_classpath:+$test_classpath:}$maven_cache/$dependency"
done

cleanup() {
  "$PG_BIN/pg_ctl" -D "$test_dir/data" -m fast stop >/dev/null 2>&1 || true
  printf 'Temporary test cluster stopped; evidence retained at %s\n' "$test_dir"
}
trap cleanup EXIT
"$PG_BIN/initdb" -D "$test_dir/data" -A trust --no-locale -E UTF8 > "$test_dir/initdb.log"
"$PG_BIN/pg_ctl" -D "$test_dir/data" -l "$test_dir/postgres.log" \
  -o "-h 127.0.0.1 -p $test_port -k $test_dir" start
"$PG_BIN/createdb" -h 127.0.0.1 -p "$test_port" workspace_adapter_test
mkdir "$test_dir/classes"
cd "$backend_dir"
javac -cp "$test_classpath" -d "$test_dir/classes" \
  storage/db/repository/PostgresSkillWorkspaceStore.java \
  storage/db/repository/SkillWorkspaceRequestSession.java \
  storage/db/repository/SkillFactoryWorkspaceFileRepository.java \
  storage/db/repository/PostgresArtifactRepository.java \
  access/ManagementIdentityProvider.java fileguard/WorkspaceSnapshot.java \
  lifecycle/domain/SkillWorkspaceFile.java storage/db/tests/PostgresSkillWorkspaceStoreLocalTest.java \
  storage/db/tests/PostgresSkillWorkspaceStoreJdbcTest.java storage/db/tests/SkillWorkspaceRequestSessionJdbcTest.java \
  storage/db/tests/PostgresArtifactRepositoryJdbcTest.java
java -cp "$test_dir/classes:$test_classpath" dev.a2flow.management.storage.db.repository.PostgresSkillWorkspaceStoreLocalTest
for test_class in PostgresSkillWorkspaceStoreJdbcTest SkillWorkspaceRequestSessionJdbcTest; do
  java -cp "$test_dir/classes:$test_classpath" "dev.a2flow.management.storage.db.repository.$test_class" \
    "jdbc:postgresql://127.0.0.1:$test_port/workspace_adapter_test"
done
java -cp "$test_dir/classes:$test_classpath" \
  dev.a2flow.management.storage.db.repository.PostgresArtifactRepositoryJdbcTest \
  "jdbc:postgresql://127.0.0.1:$test_port/workspace_adapter_test" "$(id -un)"

# Optional full Maven assembly smoke, using the exact resolved production dependencies.
if [[ -f ../target/runtime-classpath.txt && -f ../target/test-classes/dev/a2flow/management/storage/db/ManagementDatabaseConfigurationJdbcTest.class ]]; then
  java -cp "../target/classes:../target/test-classes:$(<../target/runtime-classpath.txt)" \
    dev.a2flow.management.storage.db.ManagementDatabaseConfigurationJdbcTest \
    "jdbc:postgresql://127.0.0.1:$test_port/workspace_adapter_test" "$(id -un)"
else
  printf 'MyBatis assembly smoke not run: run Maven test-compile dependency:build-classpath first.\n'
fi
