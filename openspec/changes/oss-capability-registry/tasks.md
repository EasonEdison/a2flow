# 业务能力注册平台 Phase 1 任务

## 状态说明

`tasks.md` 只记录未来实现/可执行验证。基线对齐事实记录在本任务 checkpoint。共享接口未获 main-brain 命名 revision 前，不实现依赖共享 schema 的服务代码。

## 0. 独立契约样例

- [x] 0.1 在 `services/capability-registry/` 提供合成 ability、execute_ability 调用、授权失败、版本失配、成功/业务失败结果样例。
- [x] 0.2 用现有轻量工具验证 JSON 语法、可信字段不进入 modelArguments、失败样例 adapterCalled=false 等本地不变量。
- [x] 0.3 将样例明确标记为 PROVISIONAL，不作为共享 contracts 定稿。

## 1. 共享契约接入门禁

- [ ] 1.1 main-brain 命名已审阅的 contracts revision。
- [ ] 1.2 接入共享 TrustedContext、Environment、ReleaseRef、CredentialRef 和错误包络。
- [ ] 1.3 接入共享 resolver/version guard 与 AuthorizationDecision。
- [ ] 1.4 接入共享 ResultInterpretationPolicy，不新增领域私有 DSL。

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
- [ ] 5.3 验证 Runtime 唯一成功解释器及 A2UI successPolicyRef 选择。
- [ ] 5.4 验证一次 Tool call 最多一次 adapter 调用，Runtime 不做业务自动重试。

## 6. 准出

- [ ] 6.1 执行聚焦契约测试和 PostgreSQL 多实例集成测试。
- [ ] 6.2 回填 method/params/result 字段级断言及实际命令输出。
- [ ] 6.3 通过来源/凭证/环境隔离负向测试。
- [ ] 6.4 所有必需门禁有实际证据后再评估 readiness；禁止以源码合入替代 Runtime 证据。
