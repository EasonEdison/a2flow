# 管理数据库新实例迁移

V001 只用于新的独立管理实例；不是旧库升级或数据迁移工具。服务启动不会执行它。不要直接运行 SQL 绕过版本登记。

## 显式执行

使用 JDK 17，在管理项目根目录构建：

```sh
mvn -DskipTests package dependency:build-classpath -Dmdep.outputFile=target/runtime-classpath.txt
java -cp "target/classes:$(cat target/runtime-classpath.txt)" \
  dev.a2flow.management.storage.db.migration.ExplicitManagementMigration --apply-new-instance
```

运维环境需事先安全注入 `A2FLOW_MANAGEMENT_JDBC_URL`、`A2FLOW_MANAGEMENT_DB_USER`、`A2FLOW_MANAGEMENT_DB_PASSWORD`，不要把口令写入命令历史或仓库。URL 必须为 PostgreSQL。迁移角色需具备目标数据库 public schema 建表权限；业务运行角色不应具备 DDL 权限。

迁移在独立事务内取得 advisory lock，创建 13 张业务表和 `a2flow_java_management_schema_history`，登记 V001 SQL 的 SHA-256。异常整体回滚。重复执行只有版本、校验和、表存在均符合时才返回已完成，不重建表。版本或校验和不匹配、存在未登记业务表时拒绝执行，绝不覆盖/删除旧表。已部署的 V001 不可编辑；后续演进需新增经过审查的版本及执行逻辑。当前回放校验不是完整结构漂移检测工具。

## 表边界

11 张元数据表：`agent_observation_event`、`skill_asset_release_state`、`skill_capability_action_draft`、`entity_relation`、`skill_asset_principal`、`skill_factory_authoring_event`、`skill_factory_authoring_session`、`skill_factory_authoring_turn`、`skill_component_registry`、`skill_draft`、`workflow_definition`。

所有实体关系继续共用 `entity_relation` 的实体类型和关系类型，不新增资产专属关系表。Java Long 使用 BIGINT，Integer 使用 INTEGER，自增主键使用 identity；毫秒时间保留 BIGINT。现有 JSON 字符串列使用 TEXT，与现有 MyBatis 绑定一致；不擅自更换 JSONB handler。

共享资产表保持既有 BYTEA 文档契约：`a2flow_management_drafts` 和 `a2flow_asset_versions`。namespace/kind/asset_key 分隔资产；Skill 工作区命名空间是 `skill-workspace:` 加主 namespace 的 SHA-256 hex。不可变构建包的 BUILD_ARTIFACT 不是 Runtime 已发布配置。此迁移不创建 Runtime serving 表或 publication receipt 表；运行端桥接迁移由运行端独立管理。

不创建或修改 `users`、`sessions`；鉴权必须复用已有账号体系。新管理实例必须通过宿主接入已有账号数据，不能靠本迁移生成账号。当前元数据 mapper 并非全部带 namespace，因此仅支持一个受信 namespace 的独立实例，不声明支持多租户共库。

## SQL 装配与验证

MyBatis 工厂必须加载 `classpath*:storage/db/mapper/*.xml`。Workflow 的五个自定义方法在 XML 中实现 PostgreSQL 主键回填、`(update_time,id)` keyset 分页和 revision CAS。禁止以 offset 代替分页或绕过 CAS。

独立本机验证（仅新建 loopback 临时集群，退出停止进程，保留证据）：

```sh
PG_BIN=/path/to/postgresql/bin bash backend/storage/db/tests/run-schema-migration-tests.sh
```

脚本使用当前 pom 解析出的实际依赖。覆盖首次迁移/重复执行、旧表碰撞保护、校验和拒绝、账号表未创建、11 个实体真实 mapper CRUD/主键回填/字段往返、Workflow CAS/keyset/基础更新、MyBatis 与 JDBC 同事务回滚。测试仅移除自身创建的一张单列碰撞夹具，不删除任何应用数据。
