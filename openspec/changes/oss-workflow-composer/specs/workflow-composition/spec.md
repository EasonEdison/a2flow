# Workflow Composition Capability

## ADDED Requirements

### Requirement: Phase 1 受限无环发布图

系统 MUST 支持由 sequence、AI decision condition、非嵌套 parallel region、condition MERGE、explicit JOIN、FINALIZER 组成的有限无环图。所有发布图 MUST 服务端校验全可达、引用完整和区域闭合；循环、递归、子流程及嵌套 parallel MUST 被拒绝。

#### Scenario: 发布包含顺序、条件和并行的合法图

- **WHEN** 管理员提交包含一个 AI decision、一个受限 parallel region、显式 condition MERGE 和 JOIN 的无环草稿并请求发布
- **THEN** 系统返回可解析的发布图候选，保留稳定 node/branch/candidate identity，并移除 layout 等纯编辑信息

### Requirement: AI 只从发布候选路由

AI decision MUST 从该节点发布时配置的 candidate 集合中选择一个 route。上游 Skill MUST NOT 被要求输出 Workflow 专用路由字段。AI 技术失败 MUST 保持失败，MUST NOT 被解释为语义不确定。

#### Scenario: AI 无法做出语义选择

- **WHEN** AI decision 对前驱最终结果和状态无法在配置候选中做出语义选择
- **THEN** 同一节点展示配置的 INTERACTIVE A2UI 选择卡并等待 node-bound 用户选择，合法选择直接路由且不再交给 AI 重选

### Requirement: 条件汇合与并行汇合分离

发布图 MUST 区分“已选择一个候选即可继续”的 condition MERGE 与“全部成员分支达到可 join 终态”的 parallel JOIN。未被选择的 decision candidate MUST NOT 被 JOIN 当成缺失的并行分支。

#### Scenario: 条件分支合并后进入并行 JOIN

- **WHEN** parallel 分支 A 内的 decision 选择一个候选并到达其 condition MERGE，而另一个候选从未激活
- **THEN** 分支 A 被视为到达 JOIN，未选候选不产生等待项，JOIN 只按发布的 parallel branch 成员集合判定

### Requirement: 等待分支不冻结独立分支

某分支进入 `WAITING_INTERACTION` 时 MUST 只阻塞依赖它的 JOIN，不得冻结独立分支的后继调度。JOIN MUST 读取各 branch 的持久化真实状态，而不是把一次调用或 super-step 结束当成完成。

#### Scenario: A 等待时 B1 继续到 B2

- **WHEN** parallel 分支 A 等待 A2UI 用户选择，独立分支 B 的 B1 已达到可传播成功终态
- **THEN** B2 在 A 恢复前仍被激活并可完成，B 到达 JOIN 后 JOIN 保持等待 A

### Requirement: required 与 allow-skip 保留真实结果

节点 MUST 明确区分 REQUIRED 与 ALLOW_SKIP authoring intent。成功、真实 SKIPPED、或 ALLOW_SKIP 节点的真实 FAILED 可向已配置后继/JOIN 传播；REQUIRED 节点 FAILED MUST 阻断。等待 MUST NOT 被自动改成 SKIPPED，容忍失败 MUST NOT 被改成 SUCCESS。

#### Scenario: 两类失败到达 JOIN

- **WHEN** 一个 ALLOW_SKIP 分支节点失败而另一个 REQUIRED 分支节点失败
- **THEN** 前者以 FAILED 事实满足其 branch join 条件，后者阻断 JOIN，并且两个状态都原样进入审计和最终读取

### Requirement: Skill 在对话与 Workflow 中复用

Workflow 中的 Skill 执行 MUST 统一经过 `use_skill`，并默认获得全部相关、已实际执行前序/祖先节点的最终结果和真实状态。发布图对 Skill 的引用 MUST 使用共享契约的 exact `skillKey`，或在发布边界通过显式 typed mapping 转为该 key；Composer/Runtime MUST NOT 拆 `skill:` 等字符串前缀猜测映射。发布图 MUST NOT 内嵌 Skill body、业务凭证或要求 Skill 增加 routing/branch 专用字段。中间 Tool 结果只能通过只读 retrieval Tool 读取，不能重新执行业务调用。

#### Scenario: 同一 Skill 无适配复用

- **WHEN** 同一已发布 Skill 分别从普通会话和 Workflow 节点通过 `use_skill` 调用
- **THEN** 两种入口使用同一 Skill 内容、exact `skillKey` 和 Tool 边界，Workflow 仅由 Runtime 提供通用 ancestor context，不要求修改 Skill 输出

#### Scenario: A 到 B 到 C 累积全部已执行祖先

- **WHEN** A、B 已依次完成并保存最终结果和真实状态，随后 C 被激活
- **THEN** C 的默认 context 同时包含 A、B 的最终结果和真实状态，而不是只包含直接前驱 B

#### Scenario: Join 后只汇总真实执行分支

- **WHEN** parallel 分支 A 的 decision 选择 `a_fast` 而 `a_review` 从未激活，分支 B 也完成并到达 JOIN，随后 Finalizer 被激活
- **THEN** Finalizer context 包含 A、B 真实执行祖先及 JOIN 的最终结果和状态，且不存在为未选 `a_review` 虚构的结果

### Requirement: 可信环境解析与轻量版本失配重置

Workflow、Skill、Application 等资产 MUST 按后端可信 environment/userId 通过共享 resolver 解析。PRT 只读 PRT current，ONLINE 只读 ONLINE stable/gray 且不读 PRT。run MUST 记录比较用版本；执行、continue 或 Action ingress 失配时 MUST 在新业务调用前阻断并提示 reset，MUST NOT 冻结旧配置继续、静默迁移或自动 restart。

#### Scenario: ONLINE 灰度 run 的 Action 到达时版本已变化

- **WHEN** node-bound Action ingress 使用可信 ONLINE/userId 解析出的当前版本与 run 记录版本不一致
- **THEN** 后端拒绝该 Action 的新业务调用并返回 reset-required 结果，只有用户显式 restart 才创建无继承的新 run

### Requirement: A2UI-only retry 与 Finalizer 事实边界

首版节点 retry MUST 仅对 A2UI render failure、Action call failure 或 Action result 不满足配置成功条件开放，并重入 owning node。其他 Skill/model/script/non-A2UI Tool failure MUST NOT 获得通用节点 retry。FINALIZER MUST NOT 改写真实状态、绕过 required interaction、补业务调用或在 accepted stop 后运行。

#### Scenario: A2UI Action 失败后重试 owning node

- **WHEN** A2UI Action 结果不满足配置的 success condition，用户对 owning node 发出合法 retry control request
- **THEN** Runtime 保留已完成前驱和独立分支，只重入该 owning node；业务重复调用处理仍由被调用 API 后端负责
