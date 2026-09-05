# 业务能力注册平台任务

## 状态说明

本文件只记录未来实现任务。当前 change 为 PROPOSED 设计，以下任务均未开始、未勾选；文档集成不代表设计批准或 Runtime READY。

## 0. 前置裁决

- [ ] 0.1 main-brain 批准共享资产身份、`ReleaseRef`、不可变发布包络与内容摘要规范。
- [ ] 0.2 main-brain 批准 JSON Schema 方言、MVP 关键字能力集和远程 `$ref` 策略。
- [ ] 0.3 main-brain 明确可信上下文目录及 `CredentialRef` 的所有者。
- [ ] 0.4 main-brain 明确 Runtime 调用端口的传输映射与版本策略。

## 1. 领域与持久化

- [ ] 1.1 定义 `CapabilityDraft`、草稿 revision 和验证报告领域模型。
- [ ] 1.2 定义发布 payload 与共享 `ReleaseEnvelope` 的组合。
- [ ] 1.3 使用 PostgreSQL 实现草稿、发布快照和发布幂等记录。
- [ ] 1.4 用数据库约束与事务验证多实例并发发布只有一个确定结果。

## 2. Schema 与来源绑定

- [ ] 2.1 集成经过兼容性验证的 JSON Schema 2020-12 验证器，不自研 schema 引擎。
- [ ] 2.2 实现 `modelArgumentSchema`、`resolvedInputSchema`、`outputSchema` 元校验。
- [ ] 2.3 实现 RFC 6901 Pointer 绑定解析、目标重叠检测和 required 闭合检查。
- [ ] 2.4 实现模型参数、静态常量、可信上下文三来源不可覆盖规则。
- [ ] 2.5 实现远程 `$ref` 禁止/自包含发布检查和确定性规范化摘要。

## 3. 草稿、校验与发布接口

- [ ] 3.1 实现草稿创建、按 revision 更新和读取。
- [ ] 3.2 实现显式静态校验及稳定 `ruleCode` 报告。
- [ ] 3.3 实现带幂等键的原子发布与不可变版本查询。
- [ ] 3.4 实现草稿/未发布/不支持版本的失败关闭行为。

## 4. Runtime 契约

- [ ] 4.1 产出语言中立的 `PublishedCapabilityCatalogPort` 契约。
- [ ] 4.2 产出语言中立的 `CapabilityInvocationPort`、失败分类和副作用状态契约。
- [ ] 4.3 与 Runtime 任务完成 source binding、deadline、幂等键和 trace 责任对齐。
- [ ] 4.4 与业务适配器边界完成 `CredentialRequirement`/`CredentialRef` 联调样例，不接真实企业 API。

## 5. 验证与文档

- [ ] 5.1 实现 CR-01 至 CR-08 自动化测试。
- [ ] 5.2 在两个应用实例共享 PostgreSQL 的测试中验证 revision 冲突和发布幂等。
- [ ] 5.3 验证日志、错误和事件不包含凭证明文或未经允许的业务值。
- [ ] 5.4 补充本地启动、样例适配器和公开契约说明。
- [ ] 5.5 更新 regression/readiness；只有运行证据完整后才评估 READY。
