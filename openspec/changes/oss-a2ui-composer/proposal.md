# A2UI 组件编排平台变更提案

## 状态

- 设计状态：PROPOSED
- 源码实现：未开始
- 运行态就绪：NO READY
- 审查责任人：main-brain
- 变更性质：M 侧 A2UI 组件目录、呈现草稿、校验与不可变发布产物的首轮边界提案

## 背景与问题

数字员工需要把 Agent 或 Workflow 的执行结果安全、可移植地呈现为可交互界面。若每个业务前端自行约定组件 JSON、运行时直接接受任意模型 UI、或把 React 实现细节写入 Runtime，会同时产生协议漂移、安全风险和业务耦合。

本变更提出一个定义期平台：维护受信任组件 Catalog，编排呈现草稿，进行确定性校验和编译，并通过公共发布契约产出不可变 A2UI 资产。平台不负责生产运行、流式传输、React 渲染或业务动作执行。

## 公开协议结论

截至 2026-09-06，A2UI 官方仓库将 v0.9.1 标为当前生产稳定版本，v1.0 仍为 Candidate。A2UI 定义声明式 JSON、增量 Surface 更新、Catalog 和数据绑定，并与具体传输解耦；交互场景需要有序消息、明确 framing、能力元数据和返回 action 的通道。

官方资料：

- A2UI 项目与版本状态：https://github.com/a2ui-project/a2ui
- A2UI v0.9.1 协议：https://a2ui.org/specification/v0.9.1-a2ui/
- Catalog 识别、协商与版本：https://a2ui.org/concepts/catalogs/
- Renderer 开发边界：https://a2ui.org/guides/renderer-development/
- AG-UI 交互层定位：https://github.com/ag-ui-protocol/ag-ui/blob/main/docs/introduction.mdx
- JSON Schema 2020-12：https://json-schema.org/draft/2020-12
- JSON 规范化候选 RFC 8785：https://www.rfc-editor.org/rfc/rfc8785.html

## 目标

1. 定义 Catalog 草稿和呈现草稿的最小生命周期。
2. 用公开 A2UI Catalog/消息模型和 JSON Schema 进行确定性校验。
3. 发布时锁定所有 Catalog、数据契约和 action 契约依赖，不允许 latest 或运行期隐式解析。
4. 生成内容可寻址、不可变、可审计的 Catalog Release 与 Presentation Release。
5. 把编排器、Runtime 通用 presentation 执行和 B 端 Web Renderer 的输入输出与失败边界说清楚。
6. 支持多实例 API：草稿并发更新、重复发布和瞬时失败均有明确语义。

## 非目标

- 不实现 React 组件、Web Renderer、页面宿主或数字员工业务体验。
- 不实现 Runtime 的流式执行、Surface 状态机、重放、action 调度或传输适配器。
- 不实现业务能力本身，也不因呈现依赖而自动调用能力。
- 不建立低代码通用编辑器、任意表达式语言、插件市场或任意 HTML/JavaScript 执行。
- 不决定最终编程语言、服务拆分、AG-UI 版本或 A2UI 最终协议版本。
- 本轮不新增代码、依赖、数据库、服务、端口或部署。

## 候选方案

### 方案 A：稳定 A2UI 直接草稿，加薄平台清单，推荐

- 草稿主体直接采用 A2UI v0.9.1 对应的 Catalog 与 Surface 结构。
- 平台清单只增加资产身份、精确依赖、输入数据契约、action 契约映射和编译元数据。
- Wire version 使用 v0.9.1，协议 family 归为 v0.9；协议适配器与领域模型隔离。
- 发布产物保留协议 profile，升级 v1.0 时发布新版本，不改写旧产物。

优点：基于官方当前稳定线，MVP 语义少、验证工具可复用、与 Renderer 的责任最清晰。缺点：未来升级 v1.0 需要显式编译迁移。

### 方案 B：直接采用 A2UI v1.0 Candidate

优点：Catalog 混用、函数调用和新能力更完整，减少未来一次升级。缺点：Candidate 仍可能变化，Renderer 支持和工具链稳定性不足，不适合作为十一月 MVP 的默认生产契约。

### 方案 C：先定义私有中立 DSL，再编译到 A2UI

优点：理论上可同时支持多个协议版本。缺点：首期需要自行定义解析、表达式、错误模型和语义映射，容易形成另一套非标准协议，增加编排器与 Runtime 的重复职责。

## 推荐

采用方案 A，并把 A2UI 版本与传输绑定留在可替换适配器边界：

- 首个实现候选固定 a2uiFamily=v0.9、wireVersion=v0.9.1、implementationVersion=v0.9.1。
- Presentation Release 不封装 AG-UI/SSE/WebSocket 外层事件；Runtime 选择并实现传输。
- main-brain 只有在 v1.0 转为稳定且 React Renderer/校验工具通过兼容矩阵后，才重新评估默认 profile。
- 不提供 v0.9 与 v1.0 的静默双读、latest fallback 或运行时自动降级。

## 拟议变更

### Catalog 草稿

Catalog 草稿包含名称、协议 profile、Catalog JSON Schema、允许的组件与声明式函数、说明和草稿修订号。Catalog 只描述组件与函数契约，不包含 React 代码、脚本或远程可执行内容。

### Presentation 草稿

Presentation 草稿包含单 Surface 模板、精确 Catalog 草稿或 Release 引用、输入数据 schema、只读数据契约引用、JSON Pointer 绑定和 action 契约映射。首期不支持任意表达式、多 Surface 协同或运行时自动调用 capability。

### 校验与编译

校验分为结构、图、绑定、依赖、安全与资源上限六层。编译将已校验草稿转换为确定性 Presentation Artifact；相同草稿修订和依赖锁必须产生相同规范化内容与 digest。

### 不可变发布

发布通过公共 platform-contracts 的资产/修订/授权/Release Port 完成。本域只提供领域 payload、依赖锁和校验报告，不重新定义公共 Release 身份。发布成功后禁止原地修改；任何变更产生新 Release。

## 依赖输入与本域输出

| 来源/去向 | 输入或输出 | 本域要求 |
| --- | --- | --- |
| oss-platform-contracts | AssetRef、ReleaseRef、授权上下文、幂等发布与 digest 契约 | 必须是精确且可校验的不可变引用；字段名待统一 |
| oss-capability-registry | capability output schema 与 action contract release | 仅用于类型校验和动作映射，不触发业务调用 |
| oss-agent-workflow-runtime | PublishedPresentationResolver 所需的不可变产物 | Runtime 负责实例化 Surface、数据投影、有序发送、重放与 action 关联 |
| oss-digital-employee | supportedCatalogIds、Renderer 能力与用户 action | Web Renderer 负责 React 映射、可访问性、本地校验、安全展示和用户交互 |
| 本域输出 | Catalog Release、Presentation Release、Validation Report | 都带协议 profile、精确依赖锁和内容 digest |

## 影响

- 新增一个独立 OpenSpec 设计 change。
- 后续实现需要 PostgreSQL 持久化草稿和不可变产物，并通过乐观并发与数据库唯一约束支持多实例。
- 不改变现有运行服务；当前仓库尚无本域实现。
- server-local main 集成仅表示设计源码已汇总，不表示设计批准、外部备份或运行态 READY。

## 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| A2UI 协议仍演进 | 锁定 profile；适配器隔离；旧 Release 不改写 |
| Catalog 与 Renderer 实现不一致 | 发布前校验 Renderer 能力清单；运行前精确协商；不按 latest 猜测 |
| 模型或作者产生非法树 | 结构、引用、环、root、资源上限和安全规则确定性校验 |
| 发布重试产生重复资产 | Idempotency-Key、草稿修订和唯一约束共同去重 |
| 多实例覆盖草稿 | expectedRevision 乐观并发；陈旧写入返回冲突 |
| 跨域契约各自冻结 | 所有跨域字段保持 PROPOSED，交由 main-brain 统一裁决 |

## 需要 main-brain 裁决

1. 是否接受首期以 A2UI v0.9.1 为稳定实现 pin、Wire version 为 v0.9.1，并把 v1.0 作为升级触发项。
2. 公共 ReleaseRef、digest 计算、Idempotency-Key 和依赖锁字段由 oss-platform-contracts 采用何种最终形态。
3. Runtime 与数字员工之间是否以 AG-UI 作为首选传输绑定；无论选择什么，本域发布产物均保持 transport-neutral。
