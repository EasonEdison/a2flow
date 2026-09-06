# Change Proposal: Phase 1 Skill 注册、发现与 use_skill 边界

> 基线：SW-P1-20260907.2
> 状态：**ALIGNMENT CANDIDATE / PROPOSED**
> Runtime 准出：**NO READY**
> 本 change 服从已集成基线；字段名和协议形状仍由 main-brain 与 `oss-platform-contracts` 审核。

## Why

Phase 1 要证明同一份 Skill 指令可以在对话和 Workflow 中原样复用，并且所有 Skill 使用只经过授权 Tool `use_skill`。Skill Registry 负责 M 侧目录、作者态版本和包校验；它不能把 Skill 固化成 Workflow 子图，不能要求 Workflow 路由输出，也不能让 Deep Agents 原生目录加载绕过统一 Tool、环境和授权边界。

## Superseded Design Removed

本修订明确撤销旧方案中的以下活跃设计：

1. 撤销 `SkillRevisionRef → WorkflowReleaseRef → SkillRelease` 两阶段发布；Skill 发布不绑定任何 Workflow。
2. 从 `PublishedSkillRef`、发布请求、校验门禁和回归场景中移除 `WorkflowReleaseRef`。
3. 撤销“Skill 发布时锁定 Workflow/Capability 依赖图”的首片要求。Skill 可以声明运行所需 Tool 的兼容性需求，但这不是固定业务子图，也不授予权限。
4. 不把 SDK 的 `skills=[directory]` 配置作为已发布 Skill 的另一条入口。Phase 1 的正文/资源加载必须由 `use_skill` 完成。
5. 撤销“设计获批前禁止一切 Phase 1 工作”的旧口径；当前已获准完成 ALIGN、消费者需求、候选包契约与合成样例。服务实现仍等待 main-brain 指定共享契约 revision。

## First Executable Slice

当前可独立交付且不依赖共享 schema 冻结的切片：

- 修订本域 OpenSpec，使 Skill 独立于 Workflow，并对齐 Python Deep Agents/LangGraph Runtime。
- 提交 `use_skill` 消费需求，要求 trusted context 注入、环境内解析、授权正文加载和版本证据。
- 提交 Agent Skills 兼容的候选包约束，不自造公共发布协议。
- 提交一份独立创作的 `evidence-first-brief` 指令 Skill；对话与 Workflow 均引用同一包和同一 Skill key。
- 提交正反校验案例：格式、越权、跨环境、原生目录绕过、脚本执行和 Workflow 专用字段。
- 做轻量静态检查并回传 main-brain，等待其按实际 diff 放行 `services/skill-registry/` 最小实现。

## Scope

### In scope

- M 侧 Skill 目录、作者态创建/编辑、不可变发布版本和包校验候选。
- 普通用户可浏览的描述性目录信息。
- 管理员作者态操作和普通用户拒绝案例。
- PRT/ONLINE 分库解析需求及 ONLINE stable/gray 的 userId 灰度需求。
- Runtime `use_skill` Tool 的消费者输入/输出、拒绝和版本证据需求。
- 独立合成样例及静态/合同验证计划。

### Out of scope

- 固定 Skill 子图、Workflow 路由字段、Skill 输出适配器或 per-Skill node factory。
- Workflow 图发布、条件/并行调度、A2UI 完成判定、业务 API 幂等。
- SDK 原生 Skill 目录作为对外已发布资产的激活入口。
- 普通用户作者态能力、脚本上传入口或任意脚本执行。
- 自建公共 release/resolver/auth schema、OCI 服务、ZIP 管理器或对象存储。
- 服务 scaffold、依赖 pin、数据库迁移和部署；这些等待接口 revision 审核。

## Recommended Boundary

### Catalog versus authorized material

目录查询只暴露 `skillKey`、名称、描述、标签和可用性等发现元数据。正文、references、assets 和任何 script bytes 不属于匿名/普通目录响应；它们只能在 Runtime 调用 `use_skill` 后，经 trusted user/environment 授权加载。

### Package

采用 [Agent Skills Specification](https://agentskills.io/specification) 的目录与 `SKILL.md` 结构作为候选作者格式。公共发布层只需给本域一个不可变、可校验、无凭证的 package reference；digest、media type、size、locator/handle 的最终字段由 contracts 单一所有。本域不要求首版自建 OCI Registry。

### Runtime entry

Deep Agents 官方支持把 Skills 目录直接传给 SDK，并按描述做 progressive disclosure；本项目有意不把已发布 M 资产直接接入该目录入口。Runtime 对模型暴露 `use_skill(skillKey)`，由后端注入 `userId` 与当前环境、解析有效版本、授权并返回指令/资源句柄。若未来内部使用 Deep Agents Backend/Middleware 投影内容，`use_skill` 仍必须是唯一授权入口。

## Environment and Authorization

- PRT 与 ONLINE 使用不同数据库；本域不提供跨库 fallback。
- PRT 只解析 PRT current。
- ONLINE 只解析 ONLINE stable 或按 trusted `userId` 命中的 ONLINE gray；不得读取 PRT，且同一时刻最多服务两个 ONLINE 版本。
- `userId`、environment、credentials 不进入模型可选择的 Tool 参数。
- 普通用户可以浏览目录，并在 B 侧通过授权 `use_skill` 使用 Skill；只有管理员可以创建、编辑、校验和发布。
- 发现元数据可见不等于正文/资源已授权。

## Cross-domain Inputs

| Owner | Skill Registry submits/needs | This task does not own |
| --- | --- | --- |
| oss-platform-contracts | trusted execution context、environment-local `resolveAsset`、不可变 package/release reference、版本比较、统一错误/授权语义 | 共享 schema、发布状态机、gray 算法 |
| oss-agent-workflow-runtime | `use_skill` Tool 消费需求、同包复用样例、loaded material 与 version evidence 需求 | Tool 实现、模型循环、继续/重置控制 |
| oss-workflow-composer | Workflow 节点只保存/传递 Skill 逻辑引用并调用同一 `use_skill` 路径 | Workflow 图与调度；Skill 发布不反向依赖 Workflow |
| oss-capability-registry | Skill 可声明 Tool/ability 兼容性信息；真实调用仍走 `execute_ability` 和其授权 | Ability schema、业务调用与业务幂等 |
| main-brain | 服务语言/packaging、共享 revision 和 `services/skill-registry/` 实现放行 | 根 manifest、依赖版本与跨域最终决策 |

## Acceptance for ALIGN

- 旧 change 中不再存在 Workflow-bound Skill publication。
- `use_skill` 请求不允许模型提供 userId/environment/credentials。
- 同一个 `evidence-first-brief` 包用于 chat 与 Workflow 示例，正文无模式分支或路由字段。
- 普通用户作者态、PRT→ONLINE/ONLINE→PRT fallback、native-directory bypass 和脚本执行均有拒绝案例。
- 所有实现与运行门禁保持 `NO READY`，直到 main-brain 指定共享契约 revision 并产生真实实现证据。
