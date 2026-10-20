#!/bin/sh
set -eu
set -a
. /run/selfhost/java.env
set +a
if [ "${1:-serve}" = migrate ]; then
  exec java -cp '/opt/management/classes:/opt/management/dependency/*' dev.a2flow.management.storage.db.migration.ExplicitManagementMigration --apply-new-instance
fi
exec java -Xms32m -Xmx256m -XX:MaxMetaspaceSize=192m -Dorg.newsclub.net.unix.library.tmpdir=/native -Dio.netty.native.workdir=/native -cp '/opt/management/classes:/opt/management/dependency/*' dev.a2flow.management.host.ManagementApplication
