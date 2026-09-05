# 回归计划

## 总体状态

- 状态：`PLANNED`
- 已执行：0
- 运行证据：无
- 说明：以下是实现后的验收契约，不是已通过的测试结果。

## R1 创建并保存合法串行草稿

- 状态：`PLANNED`
- Method：`CreateWorkflowDraft`，随后 `SaveWorkflowDraft`
- Params：`name`；`draftId`、`expectedDraftRevision=1`、含 START/2 个 SKILL/END 和 3 条边的 `graph`
- Success `data`：`draftId`、`draftRevision=2`、`status=DRAFT`、`updatedAt`
- 字段级断言：`draftId` 非空；revision 只递增一次；读取后 nodeId、edge 方向和 layout 与保存输入一致。

## R2 校验并发布合法两步链路

- 状态：`PLANNED`
- Method：`ValidateWorkflowDraft`，随后 `PublishWorkflowDraft`
- Params：`draftId`、`draftRevision=2`、`expectedDraftRevision=2`、`requestKey`
- Success `data`：校验返回 `valid=true`、空 ERROR issues、2 个 `resolvedDependencies`；发布返回 `workflowReleaseRef`、`artifactDigest`、`publishedAt`
- 字段级断言：release ref 和 digest 非空；manifest 有 2 个 steps；ordinal 为 1/2；Skill refs 与草稿固定 release 完全一致；不含 layout。

## R3 非串行图失败关闭

- 状态：`PLANNED`
- Method：`ValidateWorkflowDraft`，随后 `PublishWorkflowDraft`
- Params：含分支或环的 `draftId/draftRevision`；发布带相同 revision 和新 `requestKey`
- Expected error：校验 `data.valid=false` 且 issues 含 `GRAPH_BRANCH_NOT_SUPPORTED` 或 `GRAPH_CYCLE`；发布 `data=null`
- 字段级断言：issue 含 `nodeId` 或 `fieldPath`；没有 Workflow release、摘要或幂等成功记录产生。

## R4 非发布或浮动 Skill 引用被拒绝

- 状态：`PLANNED`
- Method：`ValidateWorkflowDraft`
- Params：Skill 节点分别引用 draft、`latest` 或调用方无权访问的 release selector
- Expected error：`data.valid=false`，issues 含 `SKILL_RELEASE_NOT_PUBLISHED`、`SKILL_RELEASE_UNAVAILABLE` 或授权错误；不得返回可发布 dependency snapshot
- 字段级断言：每个 issue 定位到具体 `nodeId`；服务端不把 selector 解析后悄悄写回固定版本。

## R5 相邻 schema 不兼容被拒绝

- 状态：`PLANNED`
- Method：`ValidateWorkflowDraft`
- Params：第一步 `outputSchemaRef=A`，第二步 `inputSchemaRef=B`，且 A/B 不相同
- Expected error：`data.valid=false`，issues 含 `STEP_SCHEMA_MISMATCH`，发布未调用或返回 `data=null`
- 字段级断言：issue 同时指出上游和下游 nodeId/schemaRef；无隐式转换、脚本或 fallback artifact。

## R6 并发保存不丢更新

- 状态：`PLANNED`
- Method：两个实例并发调用 `SaveWorkflowDraft`
- Params：同一 `draftId`、相同 `expectedDraftRevision=7`、不同 graph 内容
- Success `data`：仅一个请求返回 `draftRevision=8`；另一个返回 `data=null` 和 `DRAFT_REVISION_CONFLICT`，附当前 revision 8
- 字段级断言：数据库只有一个 revision 8 snapshot；失败请求内容未覆盖成功请求；重读 head 为 revision 8。

## R7 发布响应丢失后的幂等重试

- 状态：`PLANNED`
- Method：两次 `PublishWorkflowDraft`
- Params：相同 `draftId`、`expectedDraftRevision` 和 `requestKey`；第一次在数据库提交后模拟响应丢失
- Success `data`：第二次返回第一次已提交的同一 `workflowReleaseRef`、`artifactDigest`、`publishedAt`
- 字段级断言：仅一个 release 和一组 dependency rows；两次结果字段完全相同；没有重复发布审计成功事件。

## R8 Runtime 消费不可变 manifest

- 状态：`PLANNED`，跨域集成
- Method：`ResolvePublishedWorkflow`
- Params：已发布 `workflowReleaseRef`、Runtime 支持的 `contractVersion`
- Success `data`：`workflowReleaseRef`、`contractVersion`、`artifactDigest`、`inputSchemaRef`、`outputSchemaRef`、有序 `steps`
- 字段级断言：重复读取字节级 canonical 内容和 digest 不变；steps 连续有序且无 layout/secret/script/URL；未知版本或摘要不符返回 `data=null` 并失败关闭。
