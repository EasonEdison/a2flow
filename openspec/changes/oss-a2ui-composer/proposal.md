# A2UI 组件编排平台变更提案

## 状态

- 设计状态：`PROPOSED / PHASE 1 ALIGNED`
- Phase 1：独立契约样例与校验已实现；依赖共享接口的 registry 实现仍待 main-brain 命名契约修订并放行
- 运行态就绪：`NO READY`
- 审查责任人：main-brain
- 权威基线：`SW-P1-20260907.2`
- 审查修复已集成服务器 `origin/main`：`3eac2f9de3a7b306b62a5175dae374d550223959`
- 工程裁决：ENG-01 已接受未来 A2UI registry 后端采用 Python 小型可导入模块；不等于独立常驻服务或 IMPLEMENT 放行

## Phase 1 基线对齐

本任务只拥有：

- `openspec/changes/oss-a2ui-composer/`
- `services/a2ui-registry/`
- `packages/a2ui-contract-fixtures/`

本轮已经可以独立完成设计收敛、合成 Application 夹具和无依赖校验器。`services/a2ui-registry/` 依赖 `packages/contracts/` 的身份、环境、版本、发布、Action 结果条件与控制请求契约；在 main-brain 指定已审查的契约修订前不实现。

旧稿以下主动假设已被基线覆盖：

1. M 侧资产是 Component Catalog 与 Application；Presentation 只表示 Runtime 渲染产生的运行期输出。
2. Application 必须显式声明 `DISPLAY_ONLY` 或 `INTERACTIVE`，不得根据控件、文案或渲染结果推断是否等待。
3. Action 调用成功、业务结果成功和 `completeInteractionOnSuccess` 是三件事；交互完成也不等于 Skill 或 Workflow 完成。
4. Finalizer 不得改写业务事实，也不得绕过必需交互。
5. 节点重试仅限 `RENDER_FAILED`、`ACTION_CALL_FAILED`、`ACTION_RESULT_NOT_SUCCESS`，不得扩展为通用 Skill、模型或其他 Tool 重试。
6. execution/continue/Action ingress 都必须先比较当前有效版本；失配时阻断并要求显式 reset，不继续冻结旧资产、不自动迁移或重启。
7. 平台 `controlRequestId` 只去重控制请求；被调 API 后端负责业务幂等、重试及外部结果不确定性。
8. `userId`、PRT/ONLINE 与 ONLINE stable/gray 解析由共享可信后端契约负责；本域不接受模型或资产提供这些字段。
9. Application 渲染统一从授权 Tool `render_application` 进入。
10. 协议版本仍待跨域审查；合成夹具显式标记 `PROVISIONAL`，不冻结旧稿建议的 A2UI v0.9.1。

## 背景与问题

数字员工需要把 Agent 或 Workflow 的结果安全地呈现为声明式界面。若业务前端各自约定组件 JSON、Runtime 接受任意模型 UI，或 M 资产携带 React/脚本实现，会造成协议漂移、安全风险和业务耦合。

本变更定义 M 侧的 Component Catalog/Application 作者能力、确定性校验和不可变领域产物。它不负责 Runtime 的 Surface 状态、等待/恢复、Action 调度，也不负责数字员工的 React Host。

## 目标

1. 定义 Component Catalog 与 Application Draft/Release 的最小生命周期。
2. 定义 `DISPLAY_ONLY` 与 `INTERACTIVE` 的显式交互策略。
3. 定义 Action 业务成功条件与交互完成策略的独立配置。
4. 对组件图、绑定、Action 映射、安全与资源边界做确定性校验。
5. 通过公共发布契约输出不可变 Application 产物，不复制共享身份、环境、版本或发布语义。
6. 给 Runtime `render_application` 与数字员工 A2UI Host 提供可审查的消费需求。
7. 用项目独立创作的合成夹具证明上述静态边界。

## 非目标

- 不实现 Runtime 执行、Surface 流、等待/恢复、Action 调用、停止/重启或 Finalizer。
- 不实现 React Renderer、数字员工页面或业务场景。
- 不实现业务能力，也不因 Application 依赖自动调用能力。
- 不接受任意 HTML、JavaScript、远程插件、脚本上传或网络 schema 解析。
- 不自行冻结共享 schema、A2UI 版本或传输；后端语言遵循 ENG-01 的 Python 裁决，但 package layout/依赖仍需审查。
- 不在本轮部署、开放端口、启动后台服务、修改系统 Python 或其他系统包。

## Phase 1 交付

`packages/a2ui-contract-fixtures/` 提供两份合成 Application：

- 展示型结果卡：`DISPLAY_ONLY`，渲染后不暂停，无 Action。
- 交互型选择卡：`INTERACTIVE`，绑定 Runtime node/card/form，普通聊天不能恢复，配置选择直接路由而不经 AI 重新判断。

无依赖 Node 校验器验证资产类型、基线、临时协议状态、`render_application`、组件图、交互策略、Action 成功/完成分离、版本失配 reset、Finalizer 边界、控制请求去重、业务幂等归属和 A2UI-only retry 集合。夹具是静态契约证据，不是共享接口冻结、Runtime 或 Renderer 证据。

## 设计候选

### Component Catalog

Catalog 只声明组件、属性、结构引用和声明式函数 schema，不包含 React 代码、脚本体、远程模块或可执行插件。

### Application Draft

Application Draft 包含逻辑 Surface 模板、精确 Catalog 依赖、输入 schema、JSON Pointer 绑定、`interactionMode`、Action 映射和完成策略。首期不支持任意表达式、多 Surface 编排或运行期自动调用能力。

### 校验与编译

校验覆盖结构、组件图、绑定、Action、依赖、安全与资源上限。相同草稿修订、validatorRevision 与依赖锁必须产生相同规范化领域内容和 digest。

### 不可变发布

本域只产生 Component Catalog/Application 的领域 payload、依赖锁和 Validation Report；公共 Asset/Release 身份、授权、`userId`/环境解析、版本决议、digest 与发布幂等由 `packages/contracts/` 的唯一实现负责。

## 跨域边界

| 来源/去向 | 本域依赖或输出 | 边界 |
| --- | --- | --- |
| platform-contracts | 可信用户/环境、有效版本、ReleaseRef、ResultInterpretationPolicy、控制请求 envelope | 本域只消费，不创建第二套公共 schema |
| capability registry | ability output 与 Action contract 的精确 schema | 只用于定义期校验，不触发业务调用 |
| Runtime | `render_application`、Surface/等待/恢复/Action dispatch/失败结果 | Runtime 保持业务无关；先做版本准入 |
| digital employee | `packages/a2ui-host/` 的 Catalog 支持与 action ingress | Host 负责本地 React 映射、安全展示和可访问性 |
| 本域 | Catalog/Application 领域产物与 Validation Report | 协议版本仍为候选，依赖必须精确锁定 |

## 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 协议继续演进 | profile 保持候选并由适配器隔离；未经审查不 pin |
| Catalog 与 Host 不一致 | 发布前校验 Host 能力；运行前精确协商；失败关闭 |
| 作者生成非法树 | 校验 root、引用、环、可达性和上限 |
| 交互与完成混淆 | 强制显式 mode、successPolicyRef 和完成布尔值 |
| 版本变化导致旧卡误调用 | Action 前版本比较；失配只允许 reset |
| 将控制去重误当业务 exactly-once | schema 与夹具明确拆分两种责任 |
| 跨域契约各自冻结 | shared contract 由单一 owner 提交，main-brain 命名修订后再实现 registry |

## 需要 main-brain 裁决

1. 命名并批准 A2UI profile、wire version 与升级策略。
2. 命名 `packages/contracts/` 可供 registry 实现依赖的修订。
3. 批准 Runtime/Host 的传输 envelope 与 Action ingress 形态。
4. 批准 Application Draft/Release API 字段与 PostgreSQL 模型后再进入 IMPLEMENT。
