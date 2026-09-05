# 实现任务

> 本文件只记录未来实现工作。当前交付仅为 `PROPOSED` 设计；以下任务均未开始、均未完成。

## 1. 契约裁决

- [ ] 1.1 主控审查四层模型、环境 Pointer 范围和公共 schema 版本策略。
- [ ] 1.2 汇总六个领域回交的接口、权限、幂等、并发和失败需求，解决命名/字段冲突。
- [ ] 1.3 用 ADR 冻结传输基线、Runtime 语言、CloudEvents 使用方式和幂等键策略。

## 2. 公共 Schema

- [ ] 2.1 定义并版本化 AssetKey、RevisionRef、ReleaseRef、ActivationPointer 与 PrincipalRef schema。
- [ ] 2.2 定义 RFC 9457 扩展、稳定错误码注册表和字段级校验错误。
- [ ] 2.3 定义 CloudEvents 类型注册表、data schema、命名规则和固定兼容性样例。
- [ ] 2.4 提供 RFC 8785 + SHA-256 跨语言摘要 fixture。

## 3. PostgreSQL 正确性基础

- [ ] 3.1 设计并评审 revision、Release、Pointer、幂等记录、审计和 outbox 的 PostgreSQL 迁移。
- [ ] 3.2 实现唯一约束、事务边界和 Pointer CAS，不引入 MySQL、SQLite 或内存 fallback。
- [ ] 3.3 实现 outbox 发布和消费者持久去重。

## 4. 应用接口

- [ ] 4.1 实现 CreateRevision、CreateRelease、ActivateRelease 和 ResolveRelease。
- [ ] 4.2 接入可信认证上下文、默认拒绝权限检查与脱敏审计。
- [ ] 4.3 为六个领域提供经批准的共享契约包或 schema，不内置领域状态机。

## 5. 自动验证

- [ ] 5.1 完成错误、幂等、摘要、不可变和授权单元/契约测试。
- [ ] 5.2 用两个应用实例和 PostgreSQL 验证 revision 竞争、Pointer CAS 与同键重试。
- [ ] 5.3 验证事件重复、倒序、缺口、进程重启与 outbox 恢复。
- [ ] 5.4 完成 Runtime pin Release 和跨域最小 vertical slice。

## 6. 准出

- [ ] 6.1 记录真实 method、params、响应 data、trace 与字段级断言到 regression.md。
- [ ] 6.2 所有必需门禁满足后更新 readiness.md；在此之前保持 `NO READY`。
