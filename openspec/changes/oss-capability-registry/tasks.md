# 业务能力注册平台 Phase 1 任务

## 状态说明

`tasks.md` 同时记录已获放行的 `SW-P1-SUBSET-01` 源码切片和仍待实现的完整 Phase 1。子集完成不自动勾选 PostgreSQL、Runtime、部署或 E2E 门禁。

## 0. 独立契约样例

- [x] 0.1 在 `services/capability-registry/` 提供合成 ability、execute_ability 调用、授权失败、版本失配、成功/业务失败结果样例。
- [x] 0.2 用现有轻量工具验证 JSON 语法、可信字段不进入 modelArguments、失败样例 adapterCalled=false 等本地不变量。
- [x] 0.3 将样例明确标记为 PROVISIONAL，不作为共享 contracts 定稿。

## 1. 共享契约接入门禁

- [ ] 1.1 main-brain 命名已审阅的 contracts revision。
- [ ] 1.2 接入共享 TrustedContext、Environment、ReleaseRef、CredentialRef 和错误包络。
- [ ] 1.3 接入共享 resolver/version guard 与 AuthorizationDecision。
- [x] 1.4 接入 `SW-P1-SUBSET-01` 批准的 shared ResultInterpretationPolicy；只使用 SCHEMA_VALID/JSON_POINTER_EQUALS，不新增 ResultCondition AST 或领域私有 DSL。

## 2. 领域与 PostgreSQL

- [ ] 2.1 定义 AbilityDraft、schema/binding/success policy payload 领域模型。
- [ ] 2.2 使用 PostgreSQL 实现草稿、验证报告、发布 payload repository。
- [ ] 2.3 显式配置 PRT/ONLINE 分库，不提供跨环境读取和数据库 fallback。
- [ ] 2.4 用 revision/唯一约束验证多实例编辑与发布竞争。

## 3. 静态验证

- [ ] 3.1 接入成熟 JSON Schema 2020-12 验证器并记录许可证/兼容能力。
- [ ] 3.2 实现 schema、Pointer 绑定、来源闭合和常量类型验证。
- [ ] 3.3 验证 trusted context/credential 不可由模型或常量提供。
- [ ] 3.4 验证命名 success policy 与 output schema 一致，不执行任意脚本。

## 4. Registry 接口

- [ ] 4.1 实现管理员草稿创建、revision 更新、显式验证和发布。
- [ ] 4.2 实现普通用户只读发现与授权读取边界。
- [ ] 4.3 提供环境内有效 ability 数据供共享 resolver 使用。
- [ ] 4.4 对未发布、跨环境、版本不支持和摘要不一致失败关闭。

## 5. Runtime 契约验证

- [ ] 5.1 与 Runtime 验证 execute_ability 模型 schema 不暴露 userId/environment/credential/version。
- [ ] 5.2 验证版本失配与授权失败发生在 adapter 调用前。
- [ ] 5.3 验证 Runtime 唯一成功解释器、严格 JSON Pointer 语义及 A2UI 对精确 release 的 successPolicyRef 选择。
- [ ] 5.4 验证一次 Tool call 最多一次 adapter 调用，Runtime 不做业务自动重试。

## 6. 准出

- [ ] 6.1 执行聚焦契约测试和 PostgreSQL 多实例集成测试。
- [ ] 6.2 回填 method/params/result 字段级断言及实际命令输出。
- [ ] 6.3 通过来源/凭证/环境隔离负向测试。
- [ ] 6.4 所有必需门禁有实际证据后再评估 readiness；禁止以源码合入替代 Runtime 证据。

## 7. SW-P1-SUBSET-01 源码切片

- [x] 7.1 提供 immutable publication metadata、adapter operation catalog port 与 shared policy validator port。
- [x] 7.2 对 authored Ability 做字段闭合、model/server 来源隔离、RFC 6901 target 冲突和 required 来源闭合校验。
- [x] 7.3 校验 adapter input path 与 opaque credential slot 元数据兼容性，不读取 credential value。
- [x] 7.4 通过 `SharedResultPolicySetValidator` 保真映射共享 Contracts issue；不实现第二套结果解释器。
- [x] 7.5 完成 Python 3.11 单元测试、import smoke、fixture、范围和 clean-room 源码证据。
- [ ] 7.6 PostgreSQL、发布接口、resolver/admission、Runtime 接入、部署和 E2E 仍按原 Phase 1 门禁推进。
