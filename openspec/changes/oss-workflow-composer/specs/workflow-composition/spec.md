# Workflow Composition Capability

## ADDED Requirements

### Requirement: 受限串行 Workflow 草稿

系统 MUST 允许作者创建和保存由一个 START、一个 END 及 1 至 8 个 SKILL 节点组成的草稿。草稿 MUST 使用 nodes/edges 表达编辑关系，layout MUST 与执行语义分离。草稿保存 MAY 接受尚未满足发布语义的中间状态。

#### Scenario: 保存尚未连完的草稿

- **WHEN** 作者以当前 `expectedDraftRevision` 保存结构可解析但存在悬空 Skill 节点的草稿
- **THEN** 系统保存新 draft revision，并明确保持 `DRAFT`，且不把它标记为可发布

### Requirement: 服务端权威图校验

系统 MUST 在校验和发布时检查唯一节点标识、单入口单出口、全可达、无环和每个非端点入度/出度为 1。客户端限制 MUST NOT 替代服务端校验。

#### Scenario: 分支或环阻断发布

- **WHEN** 作者校验或发布包含多出边分支或有向环的草稿 revision
- **THEN** 系统返回稳定 issue code 和 node/field 定位，发布失败且不产生 release

### Requirement: 只引用已发布 Skill release

每个 SKILL 节点 MUST 引用精确、已发布、可访问的 `skillReleaseRef`。系统 MUST NOT 接受 `latest`、版本范围、草稿引用或静默替代版本。

#### Scenario: 浮动 Skill 选择器被拒绝

- **WHEN** 草稿节点使用 `latest` 或非发布 Skill revision 并请求校验
- **THEN** 系统将校验标记为无效，定位该节点，且不生成可发布 dependency snapshot

### Requirement: 首版数据契约直通

系统 MUST 让第一步接收 Workflow 输入、后续步骤接收前一步输出，并以第一步输入和最后一步输出派生 Workflow 输入/输出 schema。首版相邻步骤 MUST 使用相同规范化 `schemaRef`，且 MUST NOT 隐式转换。

#### Scenario: 相邻步骤 schema 不一致

- **WHEN** 上游输出 schemaRef 与下游输入 schemaRef 不相同
- **THEN** 系统返回 `STEP_SCHEMA_MISMATCH` 并阻断发布，且不创建转换脚本或 fallback

### Requirement: 乐观并发草稿写入

草稿更新 MUST 携带 `expectedDraftRevision`。服务端 MUST 以 PostgreSQL 原子 compare-and-set 保护更新，旧 revision MUST NOT 覆盖新 revision。

#### Scenario: 两个实例并发更新同一 revision

- **WHEN** 两个 API 实例以同一 expected revision 提交不同草稿内容
- **THEN** 恰好一个更新成功并递增 revision，另一个返回冲突和当前 revision，成功内容不被覆盖

### Requirement: 确定性且幂等的不可变发布

发布 MUST 针对指定 draft revision 重新执行全部校验，移除 layout 和草稿字段，生成确定性 manifest 与摘要。相同发布 `requestKey` 的重试 MUST 返回同一 release；已发布 release MUST NOT 被原地修改。

#### Scenario: 发布提交后响应丢失

- **WHEN** 首次发布已提交但响应丢失，调用方用相同 requestKey 重试
- **THEN** 系统返回同一 workflowReleaseRef 和 artifactDigest，且数据库中只有一个 release

### Requirement: Runtime 消费契约与所有权边界

发布物 MUST 包含 Workflow release ref、contract version、artifact digest、输入/输出 schemaRef 和按 ordinal 排序的步骤；每一步 MUST 包含稳定 stepKey 和固定 skillReleaseRef。Composer MUST NOT 创建 Run、调度步骤、保存 checkpoint 或执行重试。

#### Scenario: Runtime 解析发布物

- **WHEN** Runtime 以受支持版本解析一个已发布 Workflow release
- **THEN** 它获得连续有序且不含 layout、secret、脚本或业务展示字段的 steps，并可用 digest 验证内容

### Requirement: 依赖与协议失效时失败关闭

Skill registry 查询超时、release 不可用、contract version 未支持或 artifact digest 不符时，系统 MUST 失败关闭。Composer MUST NOT 回退到草稿、旧 Skill 版本、其他数据库或进程内状态。

#### Scenario: 发布期间 Skill registry 不可判定

- **WHEN** 发布校验无法确认任一 Skill release 的发布和可访问状态
- **THEN** 发布失败且不生成半成品 artifact，调用方可在依赖恢复后重试
