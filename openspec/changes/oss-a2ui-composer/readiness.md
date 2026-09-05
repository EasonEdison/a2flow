# A2UI 组件编排平台准出状态

## 总结

- Design：PROPOSED
- Source delivery：READY（server-local main 已含设计内容）
- Build：NO READY
- Automated tests：NO READY
- Cross-domain contract：NO READY
- Deployment：NO READY
- Runtime：NO READY
- Archive decision：NO READY

本文件是准出唯一结论。tasks.md 即使未来全部勾选，也不能替代本文件的运行证据门禁。

## 门禁矩阵

| 门禁 | 状态 | 当前证据 | 达到 READY 的条件 |
| --- | --- | --- | --- |
| Clean-room | READY | 设计仅使用已授权需求与公开官方资料；文件清单、私有标识与敏感信息扫描通过 | 后续每次公开/外部 push 前重复门禁 |
| Source integration | READY | Worker `4b02e21567df19cc73d5905df2dc9b58eb4a2281` 已集成为 server-local main `5be65edd8c1247119b8b5680847bdabaf4fb2e93` | 外部 Git 托管仍未配置，不把本状态解释为公开备份 |
| Design completeness | PARTIAL | proposal/design/spec/tasks/regression/readiness 已形成草案 | main-brain 审查并关闭关键歧义 |
| A2UI protocol decision | NO READY | 推荐 v0.9.1 实现 pin，v1.0 为 Candidate | ADR 批准 profile、wire version 与升级触发器 |
| Common release contract | NO READY | 仅提出 ReleaseRef/digest/幂等消费需求 | oss-platform-contracts 给出并批准最终字段与语义 |
| Capability/action schema contract | NO READY | 仅提出精确 schema Release 依赖 | oss-capability-registry 对齐读取、授权和兼容规则 |
| Runtime execution contract | NO READY | 仅提出 Resolver、cursor、replay、action 需求 | Runtime 契约测试通过且无业务耦合 |
| Web Renderer contract | NO READY | 仅提出 supportedCatalogIds 与安全失败语义 | React Renderer 兼容矩阵和契约测试通过 |
| PostgreSQL implementation | NO READY | 无代码、DDL 或迁移 | 草稿、校验、发布、幂等与多实例事务实现完成 |
| Static/build validation | NO READY | 设计 diff --check 通过；服务器无 OpenSpec CLI，strict validate 未执行；尚无实现可构建 | 代码静态检查、构建和 strict spec validation 通过 |
| Automated regression | NO READY | regression.md 八项均为 PLANNED | 八项有提交 SHA、环境和字段级实际断言 |
| Deployment | NO READY | 未授权且未执行 | 另行授权后由目标部署分支执行并保存证据 |
| Runtime E2E | NO READY | 无 Surface、stream、action 或恢复证据 | 端到端证明渲染、重连、action 去重与可观察性 |

## 明确不成立的声明

当前不能宣称：

- A2UI Composer 已实现或可用。
- v0.9.1 已获架构批准。
- Catalog 与 React Renderer 已兼容。
- Runtime 已能执行或恢复 Presentation。
- 并发发布、幂等、不可变性或 PostgreSQL-only 已通过测试。
- server-local main 集成等于公开发布、离机备份、部署或运行态 READY。

## 当前阻塞项

1. main-brain 尚未裁决 A2UI profile 与传输策略。
2. 公共 ReleaseRef、digest、授权和幂等契约尚未冻结。
3. Runtime 与数字员工 Web Renderer 的消费/失败接口尚未联合确认。
4. 无实现、构建、数据库、自动化测试、部署或运行证据。

## 下一准出动作

main-brain 审查本提案，先裁决协议 profile、公共发布契约和 Runtime/Renderer 分界。只有设计获批并下发实施授权后，才可将 tasks.md 中的任务纳入执行计划。
