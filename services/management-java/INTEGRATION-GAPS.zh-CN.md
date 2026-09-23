# 管理端集成剩余缺口

> 本文是 2026-09-21 的迁移缺口基线。2026-09-22 用户已调整为手填优先；最新完成项与剩余缺口见 [手填管理端说明](MANUAL-MODE.zh-CN.md)，以下历史清单不代表最新全部状态。

## 当前结论

迁移后的管理页面和 Java 领域服务已经通过 Java 17 Maven 源码编译及前端生产构建。但这不代表应用能够启动、HTTP 接口已经接通，也不代表页面能连接真实数据库和 Python Runtime 完成编辑与发布。后续修改源码后仍需重新构建。

本清单依据当前源码和依赖注入位置整理。补齐下述七个接口，并不等于产品全部完成；应用启动、鉴权、数据库装配、部署及端到端验收仍需分别完成。

## 一、七个必需接口尚无实现

以下接口已有调用方，但没有具体实现或对应的 `@Bean` 定义，也没有默认返回成功的逻辑。按照现有组件扫描方式，必需依赖无法注入。即使页面暂时不使用某项功能，其启动时依赖也不会自动变成可选项。

| 接口 | 方法与调用方 | 需要补齐的能力 |
| --- | --- | --- |
| `ManagementIdentityProvider` | `namespace(): String`、`userId(): long`；由 `SkillWorkspaceRequestSession`、`DatabaseArtifactService` 调用 | 为 Skill 工作区读写和产物访问提供可信身份，不能使用匿名身份或直接采信客户端传入的身份。 |
| `AgentService` | `queryById(String, long): Agent`、`querySubAgent(long): List<Agent>`；由 `SkillFactoryChatRuntimeService` 调用 | Skill、业务能力、A2UI 工作台中，AI 辅助编写所需的 Agent 选择及归属校验。 |
| `SkillFactoryAiCodingModelClient` | `streamCall(LLMModelConfig, List<Message>, List<ToolCallback>): Flux<ChatResponse>`；由 `AiCodingReActEngine` 调用 | 模型输出、工具调用提议及结构化流式事件。目前只是兼容接口，不是已经实现的 Python Runtime 客户端。 |
| `SkillFactoryRunControlService` | 注册／注销取消令牌，标记运行、取消、失败、完成，查询状态及请求取消；由 `SkillFactoryChatRuntimeService`、`AgentBizTool`、`SkillFactoryMethodDispatcher` 调用 | AI 辅助编写任务的运行状态、停止／取消及终态管理。 |
| `SkillFactoryLabRuntimeQueryClient` | `queryRecentSkillRuns(QueryLabMessageListRequest)`、`querySkillRunDetail(QueryLabTraceDetailRequest)`；由最近运行和运行详情工具调用 | 查询真实执行历史、诊断信息和证据。当前保留结构化响应 Map，尚未对接 Python 接口的数据结构与错误契约。 |
| `SkillFactoryReleaseReadinessInspectionService` | `inspect(String workspaceId, Path workspacePath, String operator): ReleaseReadinessInspection`；由发布检查和证据工具调用 | 生成真实的发布准出结果与门禁证据。目前只有证据状态常量，没有生成结果的实现。 |
| `RuntimeSkillPublicationPort` | `publish(SkillDraft, ReleaseArtifact, byte[], int version, String environment, String requestId): Receipt`；由 `SkillDatabasePublishService` 调用 | 将 Skill 不可变定义及依赖写入目标 Runtime 的 PRT／ONLINE 环境。回执包含资产标识、环境、包摘要、版本 ID 和内容摘要。 |

运行控制接口的方法包括 `registerCancellationToken`、`unregisterCancellationToken`、`markRunning`、`markCancelled`、`markFailed`、`markCompleted`、`queryStatus`、`requestCancel`、`isCancellationRequested`。状态操作使用 session ID 和 invoke ID 标识运行；取消令牌方法还接收 `AtomicBoolean`。`markRunning`、`queryStatus`、`requestCancel` 返回 `SkillFactoryRunStatus`，取消检查返回布尔值。

以下内容不属于新增缺失接口：

- `A2uiBuildIdGenerator` 已由 `A2uiApplicationManifestCompilerService` 通过方法引用提供。
- 辅助编写仓储接口已有数据库实现；依赖、发布、HTTP 传输和模型事件解析接口已有具体源码实现。
- MyBatis Mapper 需要框架装配，见后文。
- `WorkspaceInitializer` 是调用处传入的回调，不是缺失实现的应用 Bean。

## 二、Java 与 Python 的对接尚未实现

Runtime 对接需要可信的服务调用认证、明确的接口地址、请求／响应校验、错误映射、超时及取消处理，以及保留运行、消息、工具、观测标识的事件转换。仅声明接口或增加 JSON DTO，并不能完成这些工作。

迁移保留的 Java 辅助编写引擎包含原实现的执行编排，但这不代表允许维护第二套 Runtime。启用执行前，必须接入已确定的 Python Runtime，并明确保留哪些入口和事件适配器。另起一套 Java Agent 循环，不算解决这项对接。

模型接口暴露的是 Spring AI 消息和工具类型，运行控制接口暴露的是本地取消令牌。这些只是迁移阶段的接口，需要显式转换为 Python 的运行／控制语义，不能直接视为已完成的 Python 对外 API。历史查询必须读取真实 Runtime 记录，不能在适配器缺失时返回空列表假装已接通。

发布必须写入并校验真实 Runtime 定义及冻结依赖，保证环境隔离、请求幂等，并依据实际落库状态返回回执。`PostgresArtifactRepository` 保存包字节，只代表构建产物已保存，不能因此标记部署成功或修改运行时生效版本指针。

发布准出需要与预期摘要、规则对应的真实工作区及 Runtime 证据。编译通过或诊断适配器缺失，都不能被标记为门禁通过。

## 三、HTTP 服务入口和鉴权尚未接入

`frontend/api.ts` 请求以下路由：

- `POST /api/management/v2/handler`：按方法分发管理操作。
- `POST /api/management/v2/bizrender`：渲染操作。
- `POST /api/management/v2/chat`：AI 辅助编写的 SSE 对话。
- `POST /api/management/v2/bindings/add`：新增绑定。
- `POST /api/management/v2/bindings/remove`：解除绑定。

候选代码已有分发器和服务入口类，但没有暴露这些路由的 HTTP Controller／Router，也没有独立应用启动入口。Java 构建生成的是类文件，不是已经配置完成的 HTTP 服务。

通用处理接口的响应需要匹配前端 SSE 消息解析；对话需要保留流式输出、错误和终态事件。ZIP／文件传输及取消操作也需要通过真实服务验证。

服务必须认证请求，取得可信的命名空间和有符号 64 位 userId，实现 `ManagementIdentityProvider`，在异步执行中保留请求身份，并校验资产权限。展示名称、客户端 Header 或任意请求字段不能直接作为凭据。userId 在 JSON 边界使用精确十进制字符串，内部按 `Long` 校验。本文不指定默认账号，也不授予默认权限。

`SkillWorkspaceRequestSession` 使用 Spring `request` 作用域及代理，需要真实 Web 请求作用域、请求生命周期、事务边界和清理回调，普通非 Web Spring 上下文不能满足。工作区会话必须与元数据修改绑定到同一个已认证请求及事务。

## 四、数据库和 MyBatis 装配尚未完成

已有 Mapper 扫描配置、Mapper、实体和仓储源码，但尚未完整提供以下生产配置：

- PostgreSQL `DataSource`：外部提供凭据，明确指定目标数据库。
- 用于构造器注入的 Spring `ObjectMapper` Bean。`JsonSupport.mapper()` 只是静态编解码工具，不会自动注册 Bean。
- MyBatis／MyBatis-Plus `SqlSessionFactory` 或 `SqlSessionTemplate`，以及 SQL 注入器／配置和事务集成。
- `PlatformTransactionManager` 及已启用的事务拦截，使 `@Transactional` 实际生效。

`ManagementArtifactConfiguration` 只提供 `PostgresArtifactRepository`，依赖已有 `DataSource`。工作区请求会话使用服务提供的 `DataSource` 和 `ObjectMapper` 创建存储；这些适配器不会自行装配应用或创建数据库表结构。

当前候选目录没有带版本管理的生产 SQL 迁移。JDBC 验证辅助代码仅创建有限测试表，已排除在生产构建之外，不能当作部署数据库结构使用。

适配器引用共享表 `a2flow_management_drafts`、`a2flow_asset_versions`；元数据映射还引用：

- `skill_draft`
- `skill_component_registry`
- `workflow_definition`
- `skill_capability_action_draft`
- `skill_asset_release_state`
- `entity_relation`
- `skill_asset_principal`
- `skill_factory_authoring_session`
- `skill_factory_authoring_turn`
- `skill_factory_authoring_event`
- `agent_observation_event`

启动前需要核实迁移归属、字段、约束、索引、CAS 并发控制及与现有数据库的兼容性。

已确认没有调用方的人工审批实体、Mapper、仓储已经删除，不能为了绕过数据库装配问题重新创建审批表。

独立 PostgreSQL 工作区／产物检查通过，只能证明相应适配器已测试的行为，不能证明 MyBatis 增删改查、请求事务装配、管理 HTTP 服务或原页面的真实数据库交互已经通过。

## 五、配置要求及剩余验收

Java 配置读取器要求使用 `A2FLOW_MANAGEMENT_CONFIG`，或系统属性 `a2flow.management.config`，指定部署环境管理的 JSON 文件。配置分区包括 `agents`、`pages`、`prompts`、`permission`、`capabilityClusters`、`mountedSkillProtocolPrompt`。

所调用功能需要的 Agent、模型、记忆、工作区、变更保护及引用提示词配置都必须提供。缺少权限配置时不授予管理员权限。可选工具扩展及引导配置保持禁用／空值，不会自动选择生产环境。

`A2FLOW_ENVIRONMENT`，或系统属性 `a2flow.environment`，必须显式指定 `PRT` 或 `ONLINE`。发布源码内部仍使用 `PREPROD` 枚举，需要在边界显式映射为 PRT 并验证。仅配置地址和环境名称，不能证明隔离或部署已完成。

除补齐接口外，还需完成以下验收：

1. 装配并启动完整应用，不使用模拟身份、假成功适配器，也不把必需服务偷偷改成可选依赖。
2. 应用经过审查的数据库结构变更，验证 Skill、业务能力、A2UI、Workflow 的真实创建、读取和更新，包括权限、回滚及 CAS 失败场景。
3. 分别验证工作区编辑、草稿提交、不可变构建、发布四个生命周期操作，并通过 PostgreSQL 验证请求作用域中的文件结构投影。
4. 按既定持久化／恢复契约替换或调整进程内状态，例如 `SessionService` 的内存 Map。现有实现不能证明支持多实例会话恢复。
5. 将辅助编写的事件历史、模型／工具执行、取消及必要的 A2UI 用户交互接入真实 Python Runtime。
6. 使用原管理页面，验证每个目标环境的发布回执及发布后的实际 Runtime 执行。

目前完成的是源码编译这一前置条件。应用启动、带鉴权的增删改查、部署、发布和端到端 Runtime 验收，仍是尚未得到验证的独立交付项。
