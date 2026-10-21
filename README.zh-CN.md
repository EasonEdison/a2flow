# A2Flow

**让 Agent 通过工作流和交互界面完成业务任务，并留下可核对的结果。**

[English](README.md) · [开始使用](docs/getting-started.md) · [当前架构](docs/current-architecture.md) · [贡献指南](CONTRIBUTING.md) · [MIT 许可证](LICENSE)

A2Flow 关注的不只是生成一段回答，而是：模型如何复用技能和业务工具，在缺少信息时向用户收集输入，继续同一个任务，并准确说明哪些操作已经发生。

管理端支持对话创建与发布资产；业务端支持对话创建个人工作流、运行预制工作流和定时执行已发布预制工作流。Chat 与 Workflow 都可生成会话内的临时交互，用户提交后自动继续。工作流的保存结果和业务异常可引用到对话，继续处理时不必重跑原业务。

## 一条完整场景

```text
定时工作流 → 通过已注册业务能力查询 → 主动报告异常
  → 右侧工作动态 → 用户选择在对话中处理
  → 临时表单补充缺参 → 提交一次 → 原任务继续
  → 调用既有能力保存复核草稿 → 查看关联执行回执
```

保存草稿不等于解决异常，“已查看”不等于业务处理完成；页面和数据均区分这些状态。

## 本地体验

需要 Python 3.11+（仓库检查）以及 Node 22.12+、npm（前端）。

```sh
git clone https://github.com/EasonEdison/a2flow.git
cd a2flow
python3 scripts/check_repository.py
cd apps/digital-employee/web
npm ci --ignore-scripts --no-audit --no-fund
npm run build
npm run preview
```

打开 **http://127.0.0.1:4173/employee/?preview=fixture**。页面会明确提示为模拟展示，可查看工作流卡片与状态；不调用模型、数据库或业务服务，也不是完整登录产品的替代品。[开始使用](docs/getting-started.md)说明当前管理端构建和真实运行前提。

新安装请使用[完整自托管指南](deploy/selfhost/README.md)：从公开基础镜像构建，创建隔离 PostgreSQL/Redis、显式管理员及 mTLS 配置。初始化和资产发布分开执行，启动不会暗中创建默认密码或写入演示业务。历史 operator Compose 仍依赖既有环境；实际验证范围见[验收记录](openspec/changes/production-foundations/readiness.md)。

## 已实现范围

状态快照：2026-10-20。验收证据对应具体链路，不代表整个系统已经达到生产级准出。

| 能力 | 范围与证据 |
| --- | --- |
| 管理端手工/对话创建 | Java 管理控制面与 Python Agent，创建/复用资产并发布到 PRT。[验收](openspec/changes/management-agent-prt-authoring/readiness.md) |
| 临时交互 | Chat/Workflow 模型生成表单，合法提交后自动继续所属任务。[验收](openspec/changes/temporary-generated-interactions/readiness.md) |
| 个人工作流 | 对话生成、注册到“我的工作流”并执行。[验收](openspec/changes/personal-workflows-in-chat/readiness.md) |
| 业务能力节点 | 模型组织入参，缺参通过临时交互补齐。[验收](openspec/changes/workflow-capability-nodes/readiness.md) |
| 工作动态与处理结果 | 手动/定时结果、异常进入对话，显式处理并关联回执。[验收](openspec/changes/oss-workflow-attention-handling/readiness.md) |
| 当前执行限制 | 产品加载器支持 1–8 个顺序节点及可选总结；不宣称支持任意 DAG。 |

历史方案还讨论了并行图等目标。判断当前能力请看[实现导览](docs/current-architecture.md)，不要把提案当成上线事实。

## 值得深入看的工程设计

- **控制面与执行分离**：Java 管理资产编写、校验和发布，Python 负责模型与工作流执行；业务数据归独立业务服务。
- **真实使用框架**：Deep Agents 提供模型/工具循环，LangGraph 提供图、检查点和中断；平台负责可信身份、资产解析、执行准入和产品状态。
- **持久化对话投递**：请求标识与续聊收件记录覆盖已接收但尚未开始的任务；已完成事件可修复历史展示，不重跑 Agent。不确定执行仍需核对。[范围与验证](openspec/changes/chat-turn-reliability/readiness.md)。
- **统一工具入口**：同一个 Skill 在 Chat/Workflow 中均通过 `use_skill` 使用；身份与环境由服务端提供，模型不能任意指定。
- **明确失败语义**：停止禁止后续执行，不撤销已发出的业务写操作；不确定结果不自动重试。控制请求去重不等于业务 exactly-once。
- **可追踪证据**：区分源码验证、部署和运行验收；尚无公开压力基准或高可用保证。

## 代码入口

| 目录 | 职责 |
| --- | --- |
| `services/management-java/` | 当前 Java 资产管理与管理端 React 页面 |
| `services/agent-workflow-runtime/` | 通用 Agent/Workflow 引擎 |
| `services/b-side-api/` | 对话、工作动态、处理任务 API |
| `apps/digital-employee/web/` | 当前业务端 React 页面 |
| `services/scheduler-mq/` | 定时与事件投递 |
| `services/a2ui-execution/`、`services/capability-execution/` | 展示和业务执行边界 |
| `services/content-service/` | 独立的内容业务示例 |
| `packages/` | 共享契约、持久化与示例 |
| `openspec/changes/` | 方案、决策和验收记录 |

[面试与源码讲解](docs/portfolio-walkthrough.md) · [已知问题与改进顺序](docs/quality-roadmap.md) · [安全说明](SECURITY.md) · [文档索引](docs/README.md)

A2Flow 自有代码使用 MIT 许可证；内嵌组件与依赖保留各自许可，见[第三方声明](THIRD_PARTY_NOTICES.md)。
