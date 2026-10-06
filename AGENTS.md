# A2Flow contributor instructions

## 管理能力语言边界（2026-10-06）

- M 资产管理、编排、编译和发布使用 Java；发布直接写入隔离的 PostgreSQL 运行材料库，不再依赖 Python publication-bridge。
- 公共账号登录允许并保留 Python，独立 accounts Host 不提供资产 CRUD；B、Agent/Workflow 和业务执行运行态继续 Python。不能因为 M Python 退役而把登录或 B 运行态迁到 Java。
- 旧 Python 管理入口已移除。保留实际被 Runtime 引用的 Skill 读取与资产校验，不根据 registry/composer 旧目录名整删。

## 运行时简化版本（2026-10-04 最新用户决定）

- 运行时按请求中的可信 environment、userId 解析最新已发布资产；资产换版不要求卡片 RESET，也不把旧资产 revision 作为业务执行门槛。
- 普通业务调用不接收 project/card expectedRevision，模型和卡片不得读取后回填版本来规避该决定。
- 内容项目仍记录内部 revision 和不可变业务历史，但不因调用方持有旧项目 revision 拒绝保存素材或用户确认。
- 保留 requestId 幂等、可信身份与环境隔离、执行占用和 UNKNOWN 安全失败；不得用自动重试、静默覆盖或降级伪造成功。
- M 端发布历史、发布草稿 CAS 和资产版本治理保持不变。

## 阅读到创作场景（2026-09-23 最新用户决定）

- 首版范围：粘贴资料、阅读观点确认、选题确认、图文正文/口播文字稿编辑定稿与下载；不自动抓取或向外部账号发布。
- 只有 M 端保留 Java。新增内容业务服务及目标运行态执行服务均为 Python，内部调用继续使用已建立的 Protobuf gRPC，数据库为 PostgreSQL。此决定覆盖下面历史 Java 确定性执行的目标架构描述，但不代表旧链路已迁移完成。
- 内容业务服务独立维护用户项目、素材、产物版本和确认，不存第二套 Agent 历史/记忆，不让 Runtime 核心依赖内容领域。
- 根协调源码集成与准出；先交付可验证业务服务和 RPC 合同，再完成 M 资产、Chat/A2UI、Workflow 和部署；各阶段必须分别陈述实际证据。

## 当前实施边界（2026-09-23）

- 已批准完整管理端迁移：`services/management-java` 保留 Java 管理、编译、发布和确定性执行；Python Deep Agents 负责 Agent 模型循环。此范围覆盖下文过时的仅 Python 转写、仅设计和暂停管理端约束。
- 当前集中完成业务能力、A2UI 与普通 Chat。Workflow 新功能、管理端 AI 辅助生成暂停，不因整目录迁移而自动启用。
- 业务执行两跳均使用 Protobuf gRPC：Python → Java 执行服务 → 业务下游。内部上下文传可信 signed int64 userId，不转发浏览器 Cookie，不增加 HTTP 业务兜底。管理页面、账号会话和发布控制面仍可使用 HTTP。
- Ability/Application 的环境与灰度选择以 Java 已发布状态为准；Python 按选中的发布身份读取同环境数据库中完整留存材料。PRT 与 ONLINE 不跨库回退。
- 新增 Python 边界必须标注参数和返回类型；固定结构使用 typed DTO，动态业务 JSON 与固定运行协议分离。生成的 RPC 契约附带类型声明。不要用全面忽略类型错误替代正确模型。
- 保存源代码、隔离数据库联调和公网部署分别验收；使用 `services/management-java/RPC-CHAT.zh-CN.md` 与验证记录，不把旧公共页面当作本轮部署结果。

## Authoring migration release (2026-09-20)

The project owner explicitly authorized adapting their existing Skill/A2UI authoring and execution implementation. This scoped release supersedes the earlier independent-source restriction for those components only. Preserve the reference workflows while adapting interfaces to this project's React/Python stack; do not import credentials, private endpoints, business data, operational logs or unrelated infrastructure. Main-brain owns integration and delivery. UI/source completion and real runtime acceptance remain separate gates.

## Current bounded release (2026-09-16)

Main-brain has released AF12 common management publication, retained-version history and configuration rollback backend work. This supersedes the historical M-side pauses below only for explicitly assigned paths. Skill registry owns asset-store and management-api changes; main-brain alone reviews and integrates. No automatic successor work, model calls, database mutation or deployment follows from this source release. Keep candidate preparation non-publishing, immutable history, trusted authorization, PRT/ONLINE isolation, userId gray routing and atomic dependency-safe serving changes. Configuration rollback never compensates business operations. Current quota and execution cursor belong in the private coordinator records, not permanent architecture requirements.

## Project identity

- The product name is A2Flow, with the tagline "Agent Workflows with Interactive UI". The user approved this name on 2026-09-07, replacing SkillWeave.
- GitHub repository: https://github.com/EasonEdison/a2flow ; the github remote uses git@github.com:EasonEdison/a2flow.git. Server-local origin and all worktree paths stay unchanged.
- Existing skillweave_contracts Python imports, historical OpenSpec paths, schema identifiers and baseline IDs remain valid internal identifiers. Do not mechanically rename them or rewrite history as part of this branding change.
- Use A2Flow in new product-facing documentation. main-brain owns GitHub synchronization after server main integration; the current engine-first scope and paused domains remain unchanged.

## Latest priority: seeded browser MVP (2026-09-11)

User-approved AF-MVP-08 supersedes the engine-only pause below for three bounded workstreams: thin PostgreSQL asset import/read adapters (oss-skill-registry), Runtime host/integration, and minimal digital-employee UI. Defer the four M authoring platforms. Read `openspec/changes/skillweave-phase1/mvp-seeded-assets-release-08.md` for exclusive paths, Tool/environment boundaries and source/live/deployment gates. Do not wait for M editors or treat synthetic execution as the real MVP. Earlier design-only and pause defaults do not revoke this scoped release.

## Previous priority: Python engine first (2026-09-07)

Read `openspec/changes/skillweave-phase1/priority-engine-first.md` (SW-P1-ENGINE-FIRST-01). Only the Python Agent/Workflow Runtime domain continues; all six other domains pause new work and preserve owned changes. This latest user instruction supersedes earlier start-all and candidate-extension approvals without changing established behavior or deployment boundaries.

## Current phase authorization (2026-09-07)

- The user authorized phase 1 execution and main-brain-led coordination. Read `openspec/changes/skillweave-phase1/baseline.md` (SW-P1-20260907.2) and `plan.md` before working. These supersede conflicting old design-only instructions and proposed languages/semantics below.
- Delta PY-01: the user permits necessary system Python replacement on this server. Runtime owns compatibility/dependency checks, a recoverable change plan and post-change verification; main-brain coordinates one executor. Do not treat replacement permission as missing. This is not an instruction to replace immediately and does not authorize other package/service/deployment changes.
- Start baseline alignment, shared contract candidates and the isolated Runtime feasibility spike now. Dependent application implementation follows main-brain's recorded interface/design review, not another user-mediated kickoff.
- Own only your existing change directory and the explicitly reserved paths in the phase 1 plan. Shared files need an exclusive owner grant. main-brain owns this AGENTS.md and the phase 1 baseline/plan.
- Runtime is Python + Deep Agents SDK + LangGraph; PostgreSQL only. Respect the baseline's Tool, PRT/ONLINE userId gray, A2UI, retry/stop/restart and clean-room boundaries. Old drafts are not authority.
- User communication, task synchronization, review and acceptance belong to main-brain. Report baseline acknowledgement, stale-design corrections, owned diff and evidence to main-brain. Runtime readiness and unapproved deployment/product scope remain separate gates.

## Source and architecture

- Write new code and specifications independently from sanitized requirements and public documentation. Do not read or copy proprietary projects, schemas, tests, fixtures or credentials into this repository.
- PostgreSQL only, including development and integration tests. No MySQL or SQLite profiles or automatic database fallback.
- The digital employee depends on generic execution contracts. Runtime core must not import business models, presentation copy or scenario-specific branches.
- M composition, generic presentation execution and B frontend rendering have separate responsibilities.
- Languages, protocol versions and shared contract details are proposals until reviewed by main-brain. Domain owners must expose dependencies rather than independently freeze incompatible interfaces.

## Server worktrees and delivery

- All Git operations and repository edits happen in the assigned server worktree. The local task cwd is only a coordination surface.
- Shared integration target is `origin/main`. Every task has a unique `codex/<task-name>/design` branch and linked worktree.
- Before editing, verify pwd, branch, status, and worktree list; fetch origin and merge origin/main. Never stash/reset/clean other work or force-push.
- Current authorization is a design slice: write only `openspec/changes/<task-name>/`. Do not edit shared files, implement application code, install dependencies, change services or deploy.
- Begin with your own `checkpoint-<actual-task-title>.md`. Never read or modify another task checkpoint. Root private main-brain checkpoint belongs to the coordinator.
- Deliver proposal.md, design.md, tasks.md, regression.md, readiness.md and one capability spec under specs/. State PROPOSED for design and NO READY for runtime; all implementation checkboxes remain unchecked.
- Tests in regression.md are planned scenarios until executed. No invented build/test/runtime evidence.
- Keep the first design bounded: scope, inputs/outputs, contract dependencies, negative cases, acceptance gates, and explicit decisions for main-brain. Do not implement the full platform in one change.
- Before commit, inspect the exact diff and run git diff --check; inspect for secrets and proprietary details. Commit only owned change files using a clearly identified automation author if no identity is configured.
- Push the worker branch. Create a separate integration worktree on a unique codex/integrate/<task-name> branch from fresh origin/main, merge the worker, verify scope and whitespace, then push HEAD:main. On a non-fast-forward rejection, fetch and merge the new origin/main, recheck, and retry without force-push. Real conflicts or failed checks are reported with evidence.
- Integrating a proposed design does not approve that design or authorize implementation. Mark source delivery separately from runtime readiness.
- Report change directory, worker SHA, integrated main SHA, verification performed, and a concise list of cross-domain decisions. Do not change titles after creating checkpoints.
