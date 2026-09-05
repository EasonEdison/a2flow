# 业务能力注册平台回归计划

## 当前结论

- 状态：PLANNED
- 已执行自动化测试：0
- 已执行集成测试：0
- 已执行 Runtime/E2E：0
- 当前 Runtime 准备度：NO READY
- 说明：以下均为计划场景和字段级断言，不是已验证证据。

## 计划矩阵

| ID | 层级 | 触发 | 计划断言 |
| --- | --- | --- | --- |
| CR-01 | 领域/持久化 | 更新请求携带过期 `expectedDraftRevision` | 返回 `DRAFT_REVISION_CONFLICT`；draftRevision 与内容均未改变 |
| CR-02 | 静态验证 | 同一最终路径被模型参数和可信上下文同时绑定 | 发布失败；报告包含稳定 ruleCode 与冲突 targetPath；无发布快照 |
| CR-03 | 静态验证 | required 最终输入字段没有任何来源 | 发布失败；报告定位缺失路径；无部分发布记录 |
| CR-04 | 安全 | 模型尝试提供可信上下文或凭证槽位 | 模型参数校验/绑定拒绝；适配器调用次数为 0；错误不回显敏感值 |
| CR-05 | 发布并发 | 两实例并发发布同一 draftRevision | 仅一个不可变 release 成功；另一个明确冲突；内容摘要稳定 |
| CR-06 | Runtime 契约 | 读取精确 release 并以三来源组装输入 | resolvedInput 字段和值符合绑定；输入 schema 通过；调用使用精确 releaseRef |
| CR-07 | 输出校验 | 适配器返回不符合 outputSchema 的成功载荷 | outcome 为 `TERMINAL_FAILURE`；不合规载荷不作为成功输出传播 |
| CR-08 | 重试边界 | 非幂等写调用超时且 effectState 未知 | outcome 为 `UNKNOWN`；Runtime 不自动重试；保留 invocationId/attemptId 证据 |

## 计划字段级断言

每个自动化用例至少断言：

- `releaseRef`、`draftRevision` 或 `invocationId` 与触发请求一致。
- 失败使用稳定 `errorCode/ruleCode`，不解析自然语言 detail。
- 成功发布的 `contentDigest` 与规范化 payload 一致。
- `PublishedCapabilityContract.contract` 包含三份 schema、绑定、凭证需求和 invocation 声明。
- 日志/事件中不存在 `CredentialRef.referenceId` 对应的凭证明文。
- 失败路径的适配器调用计数、数据库发布行数和幂等记录符合预期。

## 未来执行门禁

1. 单元/属性测试覆盖 schema 元校验、Pointer 重叠和来源闭合。
2. PostgreSQL 集成测试覆盖事务、唯一约束、重启后幂等和多实例竞争。
3. Runtime 契约测试覆盖输入组装、输出验证、deadline、`UNKNOWN` 和幂等键复用。
4. 公开样例适配器 E2E 覆盖一次成功、一次可安全重试和一次人工处理。
5. 执行命令、环境、commit、实际结果和证据链接在运行后回填；不得预写通过。

## 本轮文档检查

- `git diff --check`：提交前执行并记录到 checkpoint。
- OpenSpec strict validate：服务器未发现 OpenSpec CLI，当前计划为未执行；不为此设计切片安装依赖。
- 来源/敏感信息扫描：提交前对本 change 精确文件集执行。
