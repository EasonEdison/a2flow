# A2Flow Documentation / 文档目录

Start with the architecture guide in your preferred language. Both versions cover the same product boundaries and implementation-status snapshot.

建议先选择一种语言阅读完整架构，两份指南覆盖相同的产品边界与实现状态。

| Guide / 文档 | 中文 | English |
| --- | --- | --- |
| Project introduction / 项目介绍 | [项目首页](../README.zh-CN.md) | [Project home](../README.md) |
| Complete platform architecture / 完整平台架构 | [中文架构指南](architecture.zh-CN.md) | [English architecture guide](architecture.en.md) |

## What the architecture guides cover / 架构内容

1. Product purpose, M/B terminology, and the overall architecture diagram / 项目定位、M/B 含义与总架构图。
2. Four management platforms, digital-employee product, and generic Runtime / 四个管理平台、数字员工与通用引擎。
3. Skills, abilities, Applications, Workflows, and the end-to-end execution path / 核心对象及端到端执行链。
4. Deep Agents, LangGraph, trusted Tools, and A2UI lifecycle / 框架分工、工具边界与交互生命周期。
5. Routing, parallel joins, predecessor context, PRT/ONLINE rollout / 路由、并行汇合、前序上下文与环境灰度。
6. Persistence, retry/stop/restart, permissions, memory, and knowledge / 持久化、控制语义、权限、记忆与知识。
7. Example scenarios, repository map, and current evidence boundaries / 场景示例、代码导览与实现状态。

## Design and evidence / 设计与证据

These existing engineering records may use English, Chinese, or both. The paired architecture guides provide a bilingual introduction; they do not replace detailed acceptance records.

以下工程记录保留其原有语言。中英文架构指南提供统一入口，具体准出仍以详细证据为准。

- [Confirmed phase 1 baseline / 已确认基线](../openspec/changes/skillweave-phase1/baseline.md)
- [Engine-first priority / 引擎优先](../openspec/changes/skillweave-phase1/priority-engine-first.md)
- [Engineering decisions / 工程决策](../openspec/changes/skillweave-phase1/engineering-decisions.md)
- [Approved contract subset / 已批准契约子集](../openspec/changes/skillweave-phase1/implementation-release-01.md)
- [Workstreams / 分工与依赖](workstreams.md)
- [Management authoring, references, and comparison / 管理创建、引用与版本比较](management-authoring.md)
- [Python engineering standards / Python 工程规范](python-engineering-standards.md)
- [Runtime experiments / 运行引擎实验](../experiments/runtime-phase1/README.md)
- [Runtime readiness / 引擎准出](../openspec/changes/oss-agent-workflow-runtime/readiness.md)
- [Runtime regression evidence / 引擎回归证据](../openspec/changes/oss-agent-workflow-runtime/regression.md)

Keep language versions aligned when changing architecture. Separate confirmed policy, proposed behavior, implemented source, and runtime evidence.

修改架构时同步更新两种语言，区分已确认规则、提议行为、源码实现和实际运行证据。
