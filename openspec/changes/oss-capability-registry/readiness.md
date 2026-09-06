# 业务能力注册平台 Phase 1 准出

## 总结

**Runtime：NO READY**

`SW-P1-SUBSET-01` 已放行并完成受限 Capability Registry 源码切片；共享 Contracts 薄包稳定于 main `e7797830b09ac367db21f7dde51236e3189e77f3`。本域 19/19 单测与 import smoke 是源码证据，不是常驻服务、数据库、Runtime 调用、部署或 E2E 证据；`SW-CONTRACTS-P1-CANDIDATE.1` wire field 仍不代表完整契约已批准。

## 矩阵

| 门禁 | 状态 | 当前证据 | 仍需 |
| --- | --- | --- | --- |
| 对齐源码交付 | YES | Capability 源码/evidence 已集成 main `3884af129d8bcd0772d4517cedae7c22888475c6`，包含主控变异审查修正 `1286435737f869599a2179dc506b2dfd2d8fe725` | 后续完整 Phase 1 另行放行 |
| 基线/工程决策读取 | YES | worker 已合入 SW-P1-20260907.2、ENG-01、`SW-P1-SUBSET-01` 与稳定 Contracts main | 完整 Phase 1 仍需后续 release |
| 旧冲突移除 | PARTIAL | 已移除 ResultCondition AST、NOT_EQUALS 和隐式类型转换；保留最小 policy | A2UI/Runtime 最终接入评审 |
| 成功解释器所有权 | PARTIAL | Contracts/main-brain 收敛 Runtime 单实现；A2UI main 已统一 successPolicyRef 并拒绝旧引用 | Runtime 实现与跨域验证 |
| 共享契约 | PARTIAL | `SW-P1-SUBSET-01` 薄包稳定；16/16 Python、57/57 schema 检查通过 | full bundle、resolver/admission 与 packaging 仍未放行 |
| 合成 fixture | YES | 3 个 PROVISIONAL 文件；9 cases + 2 rejected policies 检查通过 | Runtime contract 后转为跨域证据 |
| Registry 实现 | PARTIAL | importable Python 3.11 域模块；19/19 单测与 import smoke 通过 | draft/repository/publication API、持久化和常驻服务未实现 |
| PostgreSQL | NO READY | 仅设计 | 分库 schema 与多实例证据 |
| Runtime 调用 | NO READY | 仅逻辑端口 | Python/Deep Agents Tool 契约测试 |
| 真实外部写 | NOT PLANNED | 本批明确禁止 | 需要独立授权，不是本批准出项 |
| 回归/E2E | PARTIAL | source unit 19/19、shared 16/16、schema 57/57、fixture PASS；CA-01 至 CA-12 仍为计划 | PostgreSQL、Runtime integration 与端到端证据 |

## 当前可以声明

- 已读取并对齐统一基线。
- 已按 `SW-P1-SUBSET-01` 接入最小 ResultInterpretationPolicy，保持 Runtime 单解释器归属。
- 已创建独立 Python 域模块，验证 authored Ability、model/server 来源、required binding、adapter path/credential slot，并输出 immutable publication metadata。
- 已用薄 adapter 保真映射共享 Contracts issues；未实现结果解释器。
- 已交付合成契约样例与轻量静态证据；它们明确标记为非 Runtime 证据。

## 当前不得声明

- 完整共享 wire contract 已批准。
- capability-registry 常驻服务、数据库、发布接口或部署已完成。
- Runtime、授权、环境路由、数据库或业务幂等已经验证。
- 产品或真实外部写 READY。

## 下一门禁

本源码切片已集成 main；后续按独立 release 实现 JSON Schema/output-policy 完整校验、PostgreSQL、发布接口、resolver/admission、Runtime contract 和 E2E，任何阶段都不在 Registry 增加第二解释器。
