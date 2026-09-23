# 管理端发布桥

该 HTTP 进程仅监听本机回环地址，复用现有 Python asset-store 校验器和仓储，不调用模型、不执行 Skill，也不替代 Runtime。
Java `HttpRuntimeSkillPublicationAdapter` 依次调用 `/selection` 和 `/publish`。

Java 配置 `A2FLOW_PUBLICATION_BRIDGE_URL` 必须显式指定 `http://127.0.0.1:port`，
并提供至少 32 个字符的秘密配置 `A2FLOW_PUBLICATION_BRIDGE_TOKEN`。
发布桥环境使用相同令牌。禁止提交或记录令牌值。

发布桥配置如下，除特别说明外均为必填：

- `A2FLOW_PUBLICATION_VALIDATOR_FACTORY`：已安装且受信任的 `module:function`，例如现有 `deploy.assets:bundle_validator`；不能由请求指定。
- `A2FLOW_PUBLICATION_PRT_DATABASE`、`_DSN`、`_NAMESPACE`。
- `A2FLOW_PUBLICATION_ONLINE_DATABASE`、`_DSN`、`_NAMESPACE`。
- `A2FLOW_PUBLICATION_BRIDGE_PORT`：默认 8093；监听地址始终为 127.0.0.1。

使用已安装现有项目包及 psycopg 的 Python 环境。
只有取得部署授权后才能启动 `python bridge.py`；Java 不内嵌 ProcessBuilder，也不会自动启动子进程。
这份源码不会安装系统服务。已安装业务操作目录由现有校验器工厂负责提供。

通过现有、由运维显式执行的 asset-store 流程初始化 Runtime 资产表。
对每个 Runtime 目标库分别显式执行一次 `migrations/V001__publication_receipts.sql`。
发布桥不执行 DDL，也不创建账号或用户。
PRT 和 ONLINE 数据库名必须不同；访问前必须核对实际数据库名和库内环境标记与配置一致。

## 发布事实与边界

- Java 提供不可变发布快照、来源 ID／摘要及平台 requestId。旧的直接包发布方法会拒绝缺少这些控制面事实的调用。
- ZIP 字节经过摘要和大小检查，实际内容由 Python 现有资源校验器验证。冻结的 `A2UI_APPLICATION` componentName 映射为 APPLICATION key；capabilityCode 映射为 ABILITY key。两者必须已存在于目标 Runtime 命名空间，并通过现有的完整命名空间及依赖校验。
- 旧 CARD_COMPONENT/BUSINESS_DSL/Atom 绑定不能冒充 Python 组件目录，会明确失败。不会删除 Application Action 或结果语义以通过校验。
- 所需工具名称来自这些已声明绑定，不额外授予工具权限。
- 生效版本选择使用 serving CAS 令牌。发布与持久化 receipt 插入通过现有发布器，在同一个 PostgreSQL 事务及命名空间 advisory lock 内完成。请求摘要包括包、快照、来源和环境，但不包括重试时的 CAS 令牌。相同请求重试会在核对不可变内容后返回已保存的 receipt，不会在后续发布发生后把 serving 回退。
- Receipt 表示该请求已提交的发布事实，不表示其他操作后它仍然是最新生效版本。网络结果不确定时必须使用相同 requestId 重试，不能生成新的 requestId。
- Skill 范围为 PRT CURRENT 和 ONLINE STABLE，现有 Java Skill 灰度策略保持禁用。本实现不交付灰度操作，也不代表其他全部资产类型已接入 Runtime 发布。
- 来源 ID 与快照／包摘要共同生成不可变 Runtime 版本 ID；重复 PRT 构建不会覆盖先前数字草稿版本对应的内容。既有 assetId 保持不变。

## 验证

`run-local-tests.sh` 会新建并停止一个仅监听回环地址的 PostgreSQL 集群及两个新数据库。
设置 `PG_BIN`、`PYTHON_SOURCE`（精确项目源码）和 `PYTHON_BIN`；可选设置 `PG_TEST_PORT`。
脚本不使用现有应用数据库。
测试覆盖真实 HTTP 发布、认证、Python AssetReader、环境隔离、CAS、请求冲突、依赖闭包，以及 receipt 写入失败时的事务回滚。
可选的 `JAVA_TEST_BIN` / `JAVA_TEST_CLASSPATH` 用于让已编译的 `PublicationHttpAdapterTest` 访问同一个临时发布桥。

本次核对的契约源码版本为 `4710ec0801bb8cf65129e138eb8e69c6d6cc3e0c`。
发布桥的 `BoundRepository` 明确复用现有 `_document`、`_validate_serving_closure` 及事务行为；
这些属于库的私有接口，升级库时必须重新运行本集成测试。
测试和编译通过不等于已部署，也不等于完整浏览器验收通过。
