# 手填管理端：配置与交付状态

## 2026-09-23 最新增量

业务能力两段统一使用 gRPC；Application 确定性执行及 Python Chat 持久卡片已接入。能力、18 个官方基础组件、Catalog、Application、Skill 已通过独立数据库上的真实 M HTTP 创建/保存/绑定/预发发布验证。完整配置与发布身份落入 Runtime 环境库，不返回占位发布成功。详细边界及最终 Chat 验收见 [RPC-CHAT.zh-CN.md](RPC-CHAT.zh-CN.md)。Workflow 新开发与 M 端 AI 辅助生成仍暂停。本文验证不代表公网已经部署。

## 本轮范围

2026-09-22 起，先实现 Skill、业务能力、A2UI、Workflow 的手填管理、绑定、确定性校验和发布。M 端 AI 辅助编写、模型调用、运行控制、AI 历史和 AI 调试证据检查暂缓。B 端 Python Agent/Workflow Runtime 不因此停用，也不新增 Java Agent 执行引擎。

本说明更新此前 INTEGRATION-GAPS 中有关 AI 必需依赖和数据库装配的历史结论。源码完成、隔离联调、公网部署分开验收。

## 已落地的源码

- `ManualManagementConfiguration` 显式装配手填服务，不扫描旧 AI 执行入口；暂停方法返回明确的不可用错误，不返回假成功。
- `ManualManagementExecuteService` 只从可信会话取得 userId；覆盖旧协议中的 userName/userId/operator，不允许请求参数指定执行身份。
- `CookieSessionIdentityProvider` 读取既有 `a2flow_management_session` Cookie，使用 SHA-256 摘要查 `sessions` 并关联 `users`，检查过期时间和账号角色。不重新实现密码登录、不接受裸 userId Cookie。
- 管理员角色由账号表提供，不再由另一份管理员用户名白名单授权。普通账号只读；已有资产负责人关系不额外授予普通账号编辑权限。
- `ManagementDatabaseConfiguration` 提供 PostgreSQL 连接池、MyBatis-Plus、ObjectMapper 和共用事务管理器，不自动建表。
- 工作区配置从 Agent 配置下移出，手填模式不需要提供模型密钥或 Agent 配置。
- 环境枚举与取值统一 `PRT`、`ONLINE`。已有字段如 `preprodBuild`、历史方法常量及内部文件路径不是环境枚举，暂时保留以维持前后端契约一致；不再接受 `PREPROD` 作为环境枚举值。
- Spring 6 注入及销毁注解改为 `jakarta.annotation`，避免源码能编译、运行时却不注入 `javax.annotation.Resource` 字段。

## 外部配置

| 配置项 | 用途 |
| --- | --- |
| `A2FLOW_MANAGEMENT_CONFIG` | 管理配置 JSON 文件路径；启动时读取，不是动态配置中心。 |
| `A2FLOW_MANAGEMENT_JDBC_URL` | PostgreSQL JDBC 地址；必须显式提供。 |
| `A2FLOW_MANAGEMENT_DB_USER` | 数据库账号。 |
| `A2FLOW_MANAGEMENT_DB_PASSWORD` | 数据库密码，由部署秘密配置提供，禁止提交。 |
| `A2FLOW_MANAGEMENT_DB_POOL_SIZE` | 连接池上限，默认 4，允许 1–32。 |
| `A2FLOW_MANAGEMENT_NAMESPACE` | 服务端可信工作区命名空间，不能由浏览器选择。 |
| `A2FLOW_ENVIRONMENT` | 部署环境，必须为 PRT 或 ONLINE。 |
| `A2FLOW_MANAGEMENT_PORT` | Java HTTP端口，默认8790，仅监听127.0.0.1。 |
| `A2FLOW_MANAGEMENT_BROWSER_ORIGINS` | 浏览器来源白名单，逗号分隔完整origin，不能带路径。 |
| `A2FLOW_MANAGEMENT_STATIC_DIR` | 原版管理前端构建后的dist绝对目录。 |
| `A2FLOW_ACCOUNT_LOGIN_ORIGIN` | 既有账号登录服务的loopback HTTP origin，必须显式端口。 |
| `A2FLOW_PUBLICATION_BRIDGE_URL` | Python资产发布桥接服务loopback HTTP origin。 |
| `A2FLOW_PUBLICATION_BRIDGE_TOKEN` | 服务间认证秘密；部署安全注入，禁止提交或打印。 |
| `A2FLOW_RUNTIME_RPC_MODE` | 必填 `MTLS` 或显式本机验证用 `LOOPBACK`；不会缺证书自动降级。 |
| `A2FLOW_RUNTIME_RPC_PORT` | Java 确定性执行 gRPC 端口；当前固定监听 127.0.0.1。 |
| `A2FLOW_CAPABILITY_GRPC_TARGETS_JSON` | 服务端维护 targetKey 到 PRT/ONLINE 业务 gRPC 通道配置的映射，不来自模型或浏览器。证书字段见 RPC 配置说明。 |

管理配置 JSON 的手填基础字段为 `workspaceRoot`、`workspaceChangeGuard`；按所用页面和业务能力提供 `pages`、`capabilityClusters`。工作区路径仅为数据库文件的本地投影，不是另一份持久化真相。暂停功能的 `agents`、模型、记忆和提示词配置不作为手填入口的必需项。

生产部署必须将管理表放入独立新库，并显式配置既有账号库的只读连接：`A2FLOW_ACCOUNT_JDBC_URL`、`A2FLOW_ACCOUNT_DB_USER`、`A2FLOW_ACCOUNT_DB_PASSWORD`；可选 `A2FLOW_ACCOUNT_DB_POOL_SIZE` 默认 2，范围 1–8。账号角色只授予既有 `users`、`sessions` 的查询权限，由部署秘密配置注入凭据。独立账号池开启 JDBC readOnly 和 PostgreSQL `default_transaction_read_only`，只用于原有会话查询，不参与管理事务、不运行迁移。查询失败直接失败，不回退到管理库。

只有以上四项账号连接配置全部缺省时，保留共用管理 DataSource 的隔离测试模式；部分配置或无效配置启动失败，生产不得依赖缺省模式。管理库仍使用 `A2FLOW_MANAGEMENT_JDBC_URL/DB_USER/DB_PASSWORD`，账号库不得执行管理 V001 迁移。不能因为找不到账号表就创建第二套账号或复制账号数据。HTTP已接入来源校验、认证错误响应和请求作用域；`/login`、`/logout`只代理既有账号服务，不生成另一套密码或会话。登录上游同样需要允许最终浏览器origin。账号 JDBC 网络可达性由部署层提供，不由解析器修改数据库或宿主网络。

## 启动及隔离检查

先按 `backend/storage/db/migration/README.zh-CN.md` 显式初始化新实例，不在服务启动时执行DDL，不操作已有未登记旧表。原有账号库与新管理表的部署位置仍需核对；迁移不会创建账号表。

使用JDK17构建，安全注入上表配置后运行：

```sh
mvn -DskipTests package dependency:build-classpath -Dmdep.outputFile=target/runtime-classpath.txt
java -cp "target/classes:$(cat target/runtime-classpath.txt)" dev.a2flow.management.host.ManagementApplication
```

原页面使用 `/management` 路由；刷新 `/management/**` 返回前端入口，缺失静态资源和未知API仍返回404。`handler`保留原SSE包络，`bizrender`返回原JSON包络。AI对话入口明确不可用。`bindings/add`、`bindings/remove`属于原数字员工调试绑定，不是Skill资产依赖绑定，尚未接入；禁止用假成功代替。

重复HTTP检查使用 `JAVA_HOME=/path/to/jdk17 PG_BIN=/path/to/postgresql/bin bash tests/host/run-local.sh`。脚本只新建临时数据库集群及Java进程，端口冲突时拒绝执行，结束停止进程并保留证据。测试的登录上游为协议夹具，不能作为真实密码登录验收。

## 已验证与未验证

已通过独立临时 PostgreSQL 检查：

- 文件工作区保存／恢复、revision CAS、隔离和事务回滚。
- 不可变产物保存、幂等、摘要校验及损坏拒绝。
- MyBatis 真实关系表写入、PostgreSQL 自增主键回填、读取，以及与 JDBC 共用事务回滚。
- 既有会话摘要协议、精确保留 Long.MAX_VALUE 身份、角色变更、无效／过期／注销会话拒绝。

Java 17 Maven 编译与测试源码编译通过；独立权限检查验证可信 operator 匹配、普通账号禁止创建及负责人不能提升账号角色。444 个 Java 文件的 `git diff --no-index --check` 无空白错误。

真实Spring完整上下文现已启动通过；`RuntimeSkillPublicationPort`已有真实HTTP适配器，不是空实现。发布桥接复用现有Python资产校验和存储，不调用模型，独立验证进度以桥接说明为准。完整Java HTTP检查覆盖资产列表、请求作用域、PG会话、来源校验、SSE以及编辑页刷新；公网账号链路仍未验收。

追加HTTP实测已通过：管理员创建Skill、手填并保存SKILL.md、不同请求重建文件树并逐字读回内容、普通用户创建得到明确权限拒绝。测试使用配置中的合成专员和临时数据库；不冒充真实业务联调。新建工作区不自动生成SKILL.md，保持手填模式。

Skill、Capability 和 Application 现已通过真实 Java 管理 HTTP 请求发布到 Python 环境资产库；完整材料、依赖闭包、发布身份与字节摘要均留存。早期仅 Skill 桥接的验证记录不代表当前范围。Workflow 的发布到 Python Runtime 适配仍暂停，不能据此宣布四类资产全部打通。当前验证边界见 `RPC-CHAT.zh-CN.md`，发布存储机制见 `publication-bridge/VERIFICATION.md`。

新实例表结构迁移源码及隔离PG验证已完成：11张元数据表、2张共享资产表、版本校验记录、Workflow XML分页/CAS、MyBatis与JDBC共享事务回滚。没有对现有数据库执行迁移。

尚未完成：四类资产完整接口联调、原页面真实编辑／绑定／发布到Runtime验收、真实账号服务接入验收、Git集成及公网部署。独立数据库验证不能代替这些验收；现有公网服务保持不变。
