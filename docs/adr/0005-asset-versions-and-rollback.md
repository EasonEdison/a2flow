# Asset versions and rollback / 资产版本与回滚

Status: accepted design; publication and rollback operations are not implemented yet.

## Decision / 决策

The four management platforms store their assets in PostgreSQL: Skills, abilities, A2UI components/Applications, and Workflows. PRT and ONLINE use separate databases. ONLINE never reads PRT assets.

四类管理平台的资产均存储在 PostgreSQL：Skill、业务能力、A2UI 组件/Application、Workflow。PRT 与 ONLINE 分库，ONLINE 不读取 PRT 资产。

Persisted asset versions have distinct version identifiers and content digests. A different definition must not overwrite an existing version. Historical versions are distinct from serving selections: PRT has one current selection; ONLINE has one stable selection and, during rollout, at most one gray selection targeted by userId. The limit on serving versions is not a limit of two historical records.

资产版本使用独立版本标识和内容摘要；不同内容不得覆盖已有版本。历史版本与生效版本分开管理：PRT 使用当前版本，ONLINE 使用稳定版本，并可同时存在一个按 userId 命中的灰度版本。“最多两个版本生效”不表示历史只能保留两个版本。

The current draft repository retains the latest draft. Its revision supports optimistic concurrency, not a complete edit-history log. Do not present draft revision numbers as recoverable historical releases.

当前草稿存储只保留最新草稿，revision 用于乐观并发控制，并不代表保留了每次编辑历史，不能把草稿修订号展示为可回滚的发布版本。

Rollback is a future configuration-publication operation that selects a retained historical version, not a database restore. It must preserve environment isolation, authorization, dependency validation and the serving-version limits. The exact publication/rollback API and concurrency protocol remain implementation work.

回滚将通过配置发布能力，把生效选择切回已保留的历史版本，而不是恢复整库；仍须遵守环境隔离、权限、依赖校验和生效版本数量约束。具体发布/回滚接口及并发协议尚待实现。

Configuration rollback does not undo external business effects. A running Workflow detecting a configuration-version mismatch at an execution ingress must request a reset; it must not silently switch logic or replay business writes.

配置回滚不撤销已经执行的业务操作。运行中的 Workflow 在执行入口检测到配置版本不一致时，应提示重置，不得静默切换执行逻辑或重放业务写操作。

## Implementation boundary / 实现边界

Version storage and environment-aware reads exist. Management can save and validate drafts and prepare publication candidates. Preparing a candidate does not publish it. There is no claim of working release, rollback or draft-history UI in this decision.

已有版本存储、环境化读取，以及草稿保存、校验和发布候选生成。生成候选不等于发布；本决策不宣称正式发布、回滚或草稿历史界面已可用。
