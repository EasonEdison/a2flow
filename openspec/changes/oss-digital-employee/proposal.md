# 数字员工首个垂直切片提案

## 状态

- Phase 1 基线：`SW-P1-20260907.2`
- 阶段：`ALIGN / CONTRACT REVIEW`
- 设计：`PROPOSED`
- Runtime：`NO READY`
- 证据等级：设计草案，未实现、未测试、未部署

## 为什么做

Phase 1 需要一个足够小、又能暴露真实工程边界的 B 端消费切片，验证数字员工可以消费通用 Runtime，而不把业务语义、交互文案或 React 渲染逻辑放入 Runtime。首片聚焦侧栏启动、节点绑定卡片/输入、配置失配重置、停止后历史只读和 reusable A2UI Host。

“会议纪要转行动项”只作为项目自造的合成 UI fixture，帮助展示字段和状态，不是已批准产品场景，也不连接真实办公系统或执行真实业务写。若 fixture 需要模拟 Action 结果，使用脚本化测试结果并明确标注，不据此声称业务 Runtime 可用。

## 候选方案

### 方案 A：产品后端防腐层 + 固定产品壳 + 可复用 A2UI Host（推荐）

- React + TypeScript 前端只访问数字员工产品后端。
- 产品后端拥有会话、工作单、产品输入校验、可信授权与 Runtime 合约适配；未来业务执行只通过获批 Tool 进入被调 API。
- 通用 Runtime 仍是 run/checkpoint/action/stop 的唯一权威；产品后端不复制状态机。
- 固定产品壳呈现导航、会话和任务级体验；可复用 A2UI Host 只渲染受信目录中的声明式 surface，并把 action 回送产品后端。

优点是业务边界清晰、可在 Runtime 协议定版前通过适配端口隔离变化，并能复用安全渲染 Host。代价是产品后端要维护读模型转换和协议适配。

### 方案 B：React 前端直接连接 Runtime

链路更短，但前端会直接承担 Runtime 身份、恢复、并发和协议差异，业务授权也容易渗入通用 Runtime。首片不推荐。

### 方案 C：产品后端输出自定义页面 JSON，不消费 A2UI

短期可控，但会形成第二套声明式 UI 协议，无法验证 M 端 A2UI 组合物的真实消费链路。首片不推荐。

## 推荐范围

首个可执行切片在 main-brain 命名接口 revision 后仅覆盖：

1. 用户从会话侧栏显式选择一个已发布 Workflow 并启动；可信后端解析 `userId` 和 PRT/ONLINE 环境，客户端不能自报灰度身份。
2. 产品 BFF 消费 Runtime 权威查询与有序事件，把进度映射为会话和节点卡片；普通聊天不修改、选择或恢复 Workflow 节点。
3. DISPLAY_ONLY Application 呈现后继续执行；INTERACTIVE Application 把输入绑定到唯一节点/Action，等待是否完成由发布配置和真实 Action 结果共同决定。
4. continue 或 Action 入口发现有效资产版本失配时，阻断新工作并显示显式重置；重置启动全新 run，不继承旧 context/checkpoint/result/interaction。
5. stop 后历史卡片只读，前端隐藏或禁用只是体验，产品后端仍必须拒绝旧卡 Action、retry 和 resume。
6. 只有 A2UI 渲染失败或 Action 失败/结果不满足配置成功条件时显示节点 retry；不得扩展到普通 Skill、模型或非 A2UI Tool retry。
7. A2UI Host 只消费获批 profile/Catalog，并产出 Renderer 支持清单；协议、事件和 Action envelope 由共享 owner 定版。

首片不做自由编排、第三方办公系统集成、真实业务写、多租户计费、知识库平台、任意自定义组件、客户端执行模型生成代码或 Runtime 状态机复制。单个 Skill 仍是 AI 执行的 instructions/resources，不编译为固定业务子图。

## 依赖与交付关系

| 依赖方 | 本任务需要的输入 | 本任务提供的输出 | 所有者 | 当前状态 |
| --- | --- | --- | --- | --- |
| `oss-platform-contracts` | 可信 `userId`/环境、有效版本比较、控制请求去重、运行事件、失配/停止错误类别 | BFF 的操作、事件、错误和查询投影需求 | 平台合约任务 | 等待命名 revision |
| `oss-workflow-composer` | 可执行 Workflow 发布引用、节点输入约束和 A2UI 节点策略 | 侧栏选择、节点输入和状态呈现需求 | Workflow 组合任务 | `PROPOSED` |
| `oss-agent-workflow-runtime` | 启动/查询/事件/节点 Action/stop/reset/A2UI retry 语义 | 不含业务模型的 BFF 消费需求与状态样例 | Runtime 任务 | 等待基线修订；`NO READY` |
| `oss-a2ui-composer` | 协议 profile、精确 Catalog/Presentation Release、交互模式、Action 成功/完成策略 | Renderer 能力清单、安全渲染和 Action 回传需求 | A2UI 组合任务 | 等待基线修订 |
| `oss-capability-registry` | `execute_ability` Tool 的 typed result 与配置成功判定 | Tool 消费边界；业务幂等/重试归被调 API | Capability 注册任务 | 等待命名 revision |

Runtime 必须输出可排序、可去重、可重放的通用事件；不得输出本示例字段或产品文案作为核心类型。数字员工只消费 contracts owner 批准的 revision：公共事件若采用 CloudEvents，以 `(source,id)` 去重；单 run 进度按 Runtime 的 `runId + sequence` 连续消费。这里不新建第二套事件或 Action schema。

## 专属文件范围

- 本轮修订：`openspec/changes/oss-digital-employee/`。
- 接口审核放行后：`apps/digital-employee/`、`packages/a2ui-host/`。
- 共享 contracts、Runtime、M 端代码、根依赖和协议版本不在本任务编辑范围。

## 公开资料依据

- A2UI v1.0 Candidate 将声明式 UI surface 与传输解耦，并定义增量 component/data model 更新：<https://github.com/a2ui-project/a2ui/blob/main/specification/v1_0/docs/a2ui_protocol.md>
- AG-UI 官方事件文档描述 snapshot/delta 与流事件类别：<https://docs.ag-ui.com/concepts/events>

这些资料只支持候选比较，不表示本 change 已选定具体协议版本或 wire schema。

## 成功条件

- 产品后端和 Runtime 的所有权、输入输出、失败、重试、stop/reset 和并发边界可独立审查。
- A2UI Host 只渲染受信 catalog，不执行服务端下发的任意代码。
- 状态样例覆盖侧栏启动、节点输入、显示/交互边界、版本失配重置、A2UI-only retry 和停止后只读。
- 所有实现与运行证据保持未完成，直到 main-brain 命名接口 revision 并执行真实验证。

## 需要主控裁决（最多三项）

1. contracts owner 的哪一个命名 revision 作为可信上下文、运行事件、Action、配置失配与 stop/reset 的首个消费基线。
2. A2UI 的获批 protocol profile、RendererCatalogSupportManifest 字段和 Action 传输映射；旧稿中的具体名称均不先视为公共契约。
3. 数字员工产品后端的语言/部署边界，以及个人长期记忆查看、删除、关闭是否满足本文的低成本门禁。
