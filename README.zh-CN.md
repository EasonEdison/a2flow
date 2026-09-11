# A2Flow

**用交互式界面连接 Agent、Skill 与工作流。**

中文 | [English](README.md)

A2Flow 是一个通用 AI 应用平台，将可复用的 Skill、业务能力、A2UI Application 和多 Skill Workflow 连接到数字员工的对话与交互体验。

架构分为四个管理平台——Skill 注册、业务能力注册、A2UI 编排、Workflow 编排——以及数字员工前后端、业务无关的 Python Agent/Workflow Runtime。

## 架构速览

- **配置与发布**：管理可复用资产，共享发布能力和环境感知的配置解析。
- **执行**：采用 Deep Agents SDK 承载 Agent，LangGraph 承载多 Skill 图执行，PostgreSQL 作为唯一关系型持久化方案。
- **交互**：按 Application 配置展示 A2UI，或暂停等待绑定到具体节点的必需交互。
- **复用**：同一 Skill 经 `use_skill` 用于对话与 Workflow；业务能力和 Application 通过受控 Tools 调用。
- **隔离**：PRT 与 ONLINE 资产数据库分离；ONLINE 根据可信 userId 在 ONLINE 版本之间灰度。

这些是已确认的架构方向，不代表所有能力均已交付。

## 文档

- [完整平台架构 — 中文](docs/architecture.zh-CN.md)
- [Complete architecture — English](docs/architecture.en.md)
- [文档目录 / Documentation index](docs/README.md)
- [工作流分工](docs/workstreams.md)
- [已确认的第一阶段基线](openspec/changes/skillweave-phase1/baseline.md)

## 当前状态

截至 2026-09-07，优先实施 Python Agent/Workflow 引擎。仓库已有共享契约与注册核心模块、A2UI fixtures、独立框架实验；完整 M 端编辑器、数字员工产品和可部署 Runtime 尚未交付。

Runtime 实验记录了 31 个通过的测试和有限范围的 PostgreSQL 跨进程验证。产品验收仍为 **NO READY**：真实模型、完整交互与控制链、多实例冲突等仍需建设。详见[准出状态](openspec/changes/oss-agent-workflow-runtime/readiness.md)、[回归证据](openspec/changes/oss-agent-workflow-runtime/regression.md)和[实验说明](experiments/runtime-phase1/README.md)。

## 仓库目录

| 目录 | 内容 |
| --- | --- |
| `docs/` | 中英文架构指南与协作导览 |
| `packages/contracts/` | 公共 schema 候选与已批准的 Python 适配 |
| `packages/a2ui-contract-fixtures/` | 合成 Application fixtures 与校验 |
| `services/skill-registry/` | Skill 注册核心模块 |
| `services/capability-registry/` | 业务能力注册核心模块 |
| `experiments/runtime-phase1/` | Agent/Workflow 框架可行性实验 |
| `openspec/changes/` | 方案、任务、规范与证据 |

源码与示例均根据脱敏需求和公开资料独立编写。首期单机运行是部署选择，不是高可用已完成的声明。
