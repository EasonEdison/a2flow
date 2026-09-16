# Asset versions and rollback / 资产版本与回滚

Status: accepted design; single-asset publication, retained-version listing and configuration rollback backend implemented in AF12.

## Decision / 决策

The four management platforms store their assets in PostgreSQL: Skills, abilities, A2UI components/Applications, and Workflows. PRT and ONLINE use separate databases. ONLINE never reads PRT assets.

四类管理平台的资产均存储在 PostgreSQL：Skill、业务能力、A2UI 组件/Application、Workflow。PRT 与 ONLINE 分库，ONLINE 不读取 PRT 资产。

Persisted asset versions have distinct version identifiers and content digests. A different definition must not overwrite an existing version. Historical versions are distinct from serving selections: PRT has one current selection; ONLINE has one stable selection and, during rollout, at most one gray selection targeted by userId. The limit on serving versions is not a limit of two historical records.

资产版本使用独立版本标识和内容摘要；不同内容不得覆盖已有版本。历史版本与生效版本分开管理：PRT 使用当前版本，ONLINE 使用稳定版本，并可同时存在一个按 userId 命中的灰度版本。“最多两个版本生效”不表示历史只能保留两个版本。

The current draft repository retains the latest draft. Its revision supports optimistic concurrency, not a complete edit-history log. Do not present draft revision numbers as recoverable historical releases.

当前草稿存储只保留最新草稿，revision 用于乐观并发控制，并不代表保留了每次编辑历史，不能把草稿修订号展示为可回滚的发布版本。

Rollback selects a retained historical version, not a database restore. It preserves environment isolation, authorization, dependency validation and the serving-version limits. A serving-document digest is the optimistic precondition; the repository serializes changes and imports with the same namespace transaction lock. Stale requests fail rather than overwrite another publication.

回滚通过配置发布能力，把生效选择切回已保留的历史版本，而不是恢复整库；保留环境隔离、权限、依赖校验和生效版本数量约束。接口使用生效配置摘要作为乐观并发条件，存储层与导入共用 namespace 事务锁；过期请求失败，不覆盖其他人的发布。

Publishing to ONLINE STABLE clears its gray selection and user list. A single-asset publication or rollback that would make a selected Application's pinned Ability version incompatible with effective user routing is rejected. Coordinated multi-asset publication is not implemented; an operator must not bypass validation to force such upgrades.

发布到 ONLINE STABLE 会清除该资产的灰度版本及用户列表。单资产发布或回滚如果导致已选 Application 绑定的业务能力版本与用户实际命中版本不一致，会被拒绝。尚未实现多资产联动发布，不能通过绕过校验来强行升级。

Configuration rollback does not undo external business effects. A running Workflow detecting a configuration-version mismatch at an execution ingress must request a reset; it must not silently switch logic or replay business writes.

配置回滚不撤销已经执行的业务操作。运行中的 Workflow 在执行入口检测到配置版本不一致时，应提示重置，不得静默切换执行逻辑或重放业务写操作。

## Implementation boundary / 实现边界

Version storage, environment-aware reads and explicit management publication APIs exist. Management can save and validate drafts and prepare candidates; preparing a candidate still does not publish it. History lists immutable retained release identifiers/digests, not a chronological audit log or every draft edit. Real isolated PostgreSQL acceptance covered competing publication, retained history, rollback, gray selection/promotion and HTTP authorization. UI and deployment evidence are recorded separately in the management MVP document.

已有版本存储、环境化读取及显式发布接口，也支持草稿保存、校验和发布候选生成；生成候选仍不等于发布。历史列表保存已发布版本标识及摘要，不是按时间排列的操作审计或完整草稿编辑记录。隔离的真实 PostgreSQL 已验证并发发布、历史保留、回滚、灰度切换和 HTTP 权限。页面及部署证据单独记录在管理台 MVP 文档中。
