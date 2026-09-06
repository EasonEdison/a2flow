# 数字员工产品与可复用 A2UI Host 设计

## 状态与约束

- Phase 1 基线：`SW-P1-20260907.2`
- 阶段：`ALIGN / CONTRACT REVIEW`
- 设计状态：`PROPOSED`
- Runtime 准备度：`NO READY`
- 交付边界：先修订消费者需求；main-brain 命名接口 revision 后才实现最小切片
- 持久化：开发、测试和部署均为 PostgreSQL-only
- 运行拓扑：产品 BFF、事件消费和 Runtime client 必须允许多实例；进程内状态只可作可丢缓存

## 1. 场景与用户旅程

首片不冻结业务场景，以项目自造的“会议纪要转行动项”合成 fixture 演示状态。它不连接真实系统、不执行真实业务写，也不把 fixture 字段带入 Runtime。用户从固定产品壳显式启动 Workflow，观察通用节点状态，在指定节点卡片输入或操作，并能理解版本失配、stop 与 fresh restart 的后果。

触发与预期：

1. **触发**：用户在会话侧栏点击已发布 Workflow；**预期**：可信 BFF 用获批共享合约启动 run，普通聊天不会隐式启动或修改它。
2. **触发**：Runtime 输出 snapshot 与有序事件；**预期**：页面恢复并连续展示节点状态，不暴露原始思维链。
3. **触发**：节点需要用户输入；**预期**：输入只提交给该卡片关联的唯一节点/Action，普通聊天不被猜作回复。
4. **触发**：DISPLAY_ONLY Application 成功渲染；**预期**：节点不因此等待，Runtime 按发布定义继续。
5. **触发**：INTERACTIVE Application 返回 Action 结果；**预期**：配置的业务成功条件和完成标志共同决定交互是否结束，Finalizer 不覆盖事实。
6. **触发**：continue 或 Action 入口发现有效配置版本已变化；**预期**：阻断新工作并提示显式 reset，reset 创建全新 run。
7. **触发**：用户 stop；**预期**：历史卡片立即只读，后端拒绝旧 Action/retry/resume，迟到结果只作事实展示。
8. **触发**：A2UI 渲染或 Action 失败；**预期**：仅所属 A2UI 节点可显示 retry；普通 Skill、模型和非 A2UI Tool 不获得通用 retry。

## 2. 模块与所有权

### 2.1 React 产品壳

拥有路由、会话侧栏、显式 Workflow 启动入口、节点卡片、连接状态、产品文案、无障碍和错误恢复入口。UI 状态至少覆盖 `STARTABLE`、`RUNNING`、`WAITING_INPUT`、`CONFIGURATION_MISMATCH`、`STOPPED_READ_ONLY` 与 terminal result；这些是权威 Runtime 状态的视图映射，不是第二套状态机。

### 2.2 可复用 A2UI Web Host

作为 `packages/a2ui-host/` 下与业务无关的 React 包，接收获批共享契约的 surface snapshot/updates 与受信 Catalog registry，输出组件树和候选 Action。Host：

- 广告 supported protocol profiles/catalogs，并产出可核对 Catalog Release/digest 与 renderer build revision 的支持清单；具体名称等待 contracts/A2UI revision。
- 只解析已批准 profile 和 Catalog；未知版本、Catalog、组件、函数或 Action 一律 fail closed。
- 不执行动态 JavaScript、HTML 或服务端表达式；组件实现来自前端本地受信注册表。
- 用 `surfaceId` 隔离渲染状态，用 snapshot 替换已知状态，用有序 update 增量更新。
- 检测序号缺口或非法 update 后冻结该 surface，显示可恢复错误并请求新 snapshot。
- 把节点绑定输入和 Action 交给产品 BFF；Host 不持有业务授权规则，不从按钮、文案或 HTTP 成功猜测交互完成。

### 2.3 数字员工产品后端

拥有身份校验、可信 `userId`/环境构造、用户会话、产品工作单、输入净化、业务文案、错误本地化、结果视图和 Runtime 防腐层。它持久化产品实体与 run/发布引用的关联，但 Runtime snapshot 是运行状态的唯一权威；产品投影可重建，不作为调度条件。

产品语义包括侧栏启动、读取聚合视图、提交节点输入/Action、显式 stop、显式 fresh reset 和受限 A2UI retry。HTTP/RPC 方法名、字段和错误码全部等待 contracts owner 命名 revision，旧稿名称不作为公共接口。

### 2.4 Runtime Client 端口

只把产品语义转换为主控批准的通用 Runtime 操作，并把 snapshot/ordered events 转换为稳定产品读模型。它保留共享 revision 要求的 control request identity、run identity、run sequence、Action 关联、期望 run/config revision 和精确发布引用，但本 change 不命名 wire 字段，也不得通过字符串解析推断事件。

### 2.5 业务 Tool 集成边界

第一切片只使用项目合成 fixture，不实现真实外部业务写。未来业务能力通过统一 `execute_ability` Tool 背后的获批调用端口接入；被调 API 后端拥有业务参数校验、授权、幂等、重试和真实结果，产品/Workflow/Runtime 不承担业务 reconciliation、跨 run 去重或补偿。

## 3. 数据所有权

| 数据 | 权威所有者 | 数字员工可持久化 | 约束 |
| --- | --- | --- | --- |
| 用户会话、工作单、节点输入引用 | 产品 BFF | 是 | PostgreSQL；避免在日志记录正文 |
| `userId`、授权与 PRT/ONLINE 选择 | 可信认证/环境边界 | 只保存审计所需引用 | 不信任客户端覆盖；ONLINE gray 不读取 PRT |
| Workflow/Ability/A2UI 发布物 | 对应 M 端平台 | 只保存精确引用、所见版本和可选缓存 | 不复制发布状态机，不继续旧有效版本 |
| run、checkpoint、Action、stop、retry、事件 sequence | Runtime | 只保存关联 ID、最后确认 sequence 和可重建投影 | Runtime snapshot 优先 |
| A2UI surface 运行快照 | Runtime/展示协议定义的权威存储 | 浏览器可缓存，产品端可作可丢投影 | 断线以 snapshot 重建 |
| 未来业务结果、业务幂等/重试 | 被调 API 后端 | 只保存业务允许的引用/结果 | 不由 Workflow 做 reconciliation 或跨 run 去重 |

产品工作单可展示处理中、待输入、配置已变化、已停止、完成或失败，但这些只是获批 Runtime snapshot/事件的 UI 映射，不是第二套状态机，也不能驱动 Runtime 迁移。

## 4. 概念接口需求（非最终 wire schema）

本节只给 contracts owner 消费需求。`StartRun`、`GetRun`、`SubscribeRunEvents`、`SubmitAction` 等是当前旧稿中的说明性候选名；`actionRequestId`、`expectedRunRevision`、Renderer 支持清单名称和错误码也尚未批准。本任务必须等待 main-brain 指定命名 revision 后才能绑定代码。

### 4.1 所需操作语义

- **侧栏启动**：可信 `userId`、PRT/ONLINE、精确 Workflow 引用、节点入口输入、控制请求去重信息；返回 run identity、初始权威状态和所见有效资产版本。
- **读取与订阅**：按 run identity 读取 snapshot，并从最后连续 run sequence 重放；返回节点状态、开放节点输入/Action、presentation、配置失配、stop 和 terminal facts。
- **提交节点输入/Action**：携带 Runtime 可验证的 run/node/Action 关联、所见 run/config revision、结构化输入与可信授权；重复同义、冲突、过期和错误节点必须机器可判定。
- **stop**：提交后禁止所有分支接纳新节点、模型/Tool round、Workflow Action 和 retry；后续查询仍返回历史事实，任何 resume 被拒绝。
- **fresh reset**：从入口创建新的 run identity；不继承旧 context、checkpoint、结果、完成标志或 interaction，也不查询旧业务结果来决定是否开始。
- **A2UI retry**：仅当权威状态明确给出“渲染失败、Action 调用失败或结果不满足配置成功条件”及所属节点时可提交；其他失败没有通用 retry 操作。

### 4.2 事件与错误语义

- 公共跨模块事件若采用 CloudEvents，消费者按 `(source,id)` 持久去重并仅把同一 aggregate version 当作顺序；这不替代 run 内 sequence。
- 运行投影必须提供单 run 严格单调 sequence、可重放缺口与 snapshot 重建语义；UI 不按到达时间或业务文案排序。
- 必须有稳定机器类别表达配置版本失配、run 已 stop、Action 冲突/过期、节点不匹配、A2UI 不支持和不可 retry；最终字段/错误码由 contracts owner 定义。

### 4.3 A2UI presentation

- Host 需要获批 protocol profile、精确 Catalog/Presentation Release 与 digest、surface snapshot/update、interaction mode、Action schema 和所属 run/node 关联。
- Renderer 需要发布其支持的 protocol/Catalog、精确 digest 和 renderer build revision，且未知资产不得 fallback、latest 或运行时下载。
- DISPLAY_ONLY 不建立等待；INTERACTIVE 建立节点绑定输入。Action 调用成功、业务结果满足配置条件、该成功是否完成 interaction 是三个不同事实。
- 产品 BFF 在 Action ingress 重新校验可信主体、环境、有效配置版本、run/node/Action 关联和 stop 状态；前端禁用不是安全边界。

### 4.4 环境与配置版本

- PRT 只读取 PRT 当前版本；ONLINE 只在 ONLINE stable/ONLINE gray 中按可信 `userId` 选择，绝不读取 PRT。
- start、continue 和 Action ingress 都比较已记录版本与当前有效版本。失配只阻断新工作并提示 reset，不继续旧资产、不静默迁移、不自动 restart 或 replay。
- Runtime 使用 Python + Deep Agents SDK + LangGraph 是已接受基线，但其内部实现不改变产品端只消费共享通用契约的边界。

## 5. 事件、恢复与并发

```text
用户 -> 产品 BFF: 侧栏显式启动（选择 Workflow 和 PRT/ONLINE）
产品 BFF -> 共享/Runtime 端口: 可信 userId + 精确发布引用 + 控制请求去重
Runtime -> 产品 BFF: snapshot + ordered run events + presentation
产品 BFF -> React/A2UI Host: 产品投影 + 节点绑定 surface
用户 -> 产品 BFF: 节点输入 / Action / stop / fresh reset / A2UI retry
产品 BFF -> 共享/Runtime 端口: 获批操作语义 + 所见 revision + 可信授权
Runtime -> 产品 BFF: 权威结果、失配/停止事实与下一 sequence
```

- **断线/缺口**：客户端只提交最后连续 run sequence；无法连续重放时获取 snapshot，不猜测缺失事件。
- **重复/倒序**：运行投影按 `runId + sequence` 去重和排序；公共事件外壳若采用 CloudEvents，再独立按 `(source,id)` 去重。
- **Action 并发**：只提交共享 revision 规定的 Action 关联与所见版本；完全相同重复返回稳定结果，矛盾、过期、错误节点或错误主体被拒绝。
- **配置失配**：start/continue/Action 入口在新工作前检查有效版本；只展示 reset 提示，不继续旧资产或自动迁移。
- **stop/restart**：stop 先提交后不接纳新工作；迟到结果只显示事实。restart 总是 fresh run，不恢复 stopped run。
- **业务失败**：业务调用的幂等与重试属于被调 API 后端；Workflow 不做业务 retry、查询旧结果、补偿或跨 run 去重。
- **多实例**：产品 BFF 不依赖 sticky session 或进程锁；会话/投影/设置等产品状态只以 PostgreSQL 为正确性真值。

## 6. 安全与可观测性

- 用户输入、presentation、Action 请求和 Tool 结果均按共享 schema、大小、深度和允许类型校验。
- `userId` 与环境由可信服务端上下文提供；客户端传入的主体或环境覆盖必须被拒绝。
- A2UI Host 仅渲染本地受信组件；链接、富文本和下载动作采用明确策略。
- 页面只展示用户可理解的活动摘要、工具结果和错误，不展示原始思维链、模型隐藏消息或密钥。
- 日志使用关联 ID 和错误类别，正文默认不入日志；审计至少记录 run/node/Action、主体、stop、fresh reset、配置失配和结果事实。
- 指标至少区分启动、重放、cursor gap、配置失配、stop 后拒绝、历史卡操作拒绝、A2UI 节点重试和 Renderer 拒绝。

## 7. 失效边界

| 失效 | 责任方 | 对用户的结果 | 禁止行为 |
| --- | --- | --- | --- |
| Runtime 不可达 | 产品 BFF | 显示连接失败并保留已知投影 | 不伪造本地运行成功 |
| 事件缺口 | Runtime Client / Host | 冻结增量并补 snapshot | 不跳过缺口继续渲染 |
| 未知 A2UI 资产 | Web Host | 安全错误卡和刷新入口 | 不降级执行任意 HTML/JS |
| 配置版本失配 | 产品 BFF + Runtime | 阻断 continue/Action 并提示显式 reset | 不继续旧版本、不静默迁移、不自动重启 |
| stopped run 上的新操作 | Runtime + 产品 BFF | 后端类型化拒绝，历史卡只读 | 不恢复 stopped run、不启动新分支 |
| 非 A2UI 节点失败 | Runtime | 显示失败事实 | 不提供通用 Skill/model/Tool 重试 |
| 业务 API 暂时失败 | 被调 API 后端 | 展示 API 返回事实 | Workflow 不重试、不查询旧结果、不补偿 |
| PostgreSQL 不可用 | 各持久化模块 | 请求失败且保持可诊断 | 不回退到内存、SQLite 或 MySQL |

## 8. 分阶段验证

1. 共享合约命名修订后，用合成 fixture 验证产品 BFF、Runtime fake 和安全 A2UI Host 的契约。
2. 在 BFF/Host 契约测试中覆盖投影顺序、节点输入、显示/交互分流、配置失配、stop、fresh reset 与 A2UI-only retry。
3. 接入真实 Runtime 后，在至少两个 BFF/worker 实例与 PostgreSQL 上验证事件重放、缺口补快照、控制并发和实例切换。
4. 等接口 owner 集成与运行证据齐备后再建立公开演示；此前始终保持 `NO READY`。

## 9. 个人长期记忆控制成本评估

基于 Deep Agents 与 LangGraph 的公开能力，成本分为三档；估算需在后续代码、依赖与权限核验后由 main-brain 定案：

- **A，约 0.5–1.5 人日**：已有 user-scoped PostgreSQL Store 适配器和获批 BFF facade；只增加一个设置页，复用分页 list/delete，并接入已有 preference。
- **B，约 2–4 人日，仍可能属于低成本**：只缺一张最小偏好元数据表/迁移、三个安全 BFF 操作和 Runtime 读写门禁；不改变记忆正文 schema、索引或检索算法。
- **B+，约 3–6 人日，需主控复核**：缺少薄 user-scoped Store adapter，但现有 PostgreSQL Store 依赖、namespace 和删除权限可直接复用；只补 adapter、授权和聚焦测试。

三档共同语义：

- BFF 只暴露当前可信 `userId` 的 list/delete/preference；关闭后停止长期记忆读取和新写入，但当前对话、当前 run 与短期上下文继续。
- 删除单条长期记忆不删除聊天记录，不伪装成“知识库删除”。

新向量索引、记忆正文 schema 改造、派生副本删除传播、导出/撤销/保留策略、组织共享、文件上传/切块、搜索质量调优或知识库管理 UI 明确不在本阶段。基础偏好元数据或薄 facade 不因“新增 schema/adapter”字样自动延期；先给最小 diff 与验证成本，由 main-brain 按低成本授权决定。

本判断只证明公开 SDK 具备 Store 与 delete 原语，不证明本仓库已经锁定精确版本、已有所需 adapter、删除权限正确、持久化 schema 兼容或生产可用。

公开依据：

- [Deep Agents memory](https://docs.langchain.com/oss/python/deepagents/memory)：长期记忆由 Backend/Store 提供，并可使用用户作用域。
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)：跨线程记忆由 Store 管理，生产环境可使用 PostgreSQL Store。
- [LangGraph BaseStore delete](https://reference.langchain.com/python/langgraph.store/base.BaseStore/delete)：Store 暴露按 namespace/key 删除的原语。

## 10. 待裁决

仅保留 proposal 中的三项主控裁决：Runtime wire 协议、A2UI/传输精确版本、产品后端及业务 Tool 交付边界。裁决前所有接口名和字段都是消费需求，不是已发布契约；应用实现等待 contracts owner 给出命名修订。

## 11. BFF 技术选项与模块路径清单

### 11.1 当前仓库证据

- 当前仓库还没有 `apps/`、Runtime 可执行模块或根级 JS/Python 工程清单，不能声称已有可直接调用的 Runtime SDK。
- `packages/a2ui-contract-fixtures/` 已提供两个 provisional Application fixture 和无依赖 validator，可作为未来 Host consumer test 输入；其字段仍是 `SW-CONTRACTS-P1-CANDIDATE.1` 候选。
- 当前 Runtime 设计稿中的具体 operation/field 与旧语言建议均不是获批接口；产品不得据此提前生成客户端或固化 DTO。

### 11.2 最小 BFF 选项

| 选项 | 最小形态 | 复用依据 | 新增成本/风险 | 当前建议 |
| --- | --- | --- | --- | --- |
| A. Python BFF | `apps/digital-employee/bff/` 独立应用模块 | contracts 的中立 schema + 未来薄 Python adapter；与 Python Runtime 减少一种客户端语言 | 必须保持进程/领域边界，不得 import Runtime 内部状态模型 | 条件推荐；待 named revision、依赖和部署边界确认 |
| B. TypeScript BFF | 与 React 工程同仓但独立 server entry | 中立 schema/examples；前端类型与 server routes 可共用生成物 | 需要额外 Runtime transport client、Python 边界测试和部署进程 | 若选定前端宿主天然提供 server runtime，再评估 |
| C. 浏览器直连 Runtime | 无 BFF | 无 | 身份、环境、版本 admission、stop 与 Action 重新授权泄漏到浏览器 | 拒绝 |

选择 A 不是由 `ENG-01` 自动推出；依据仅是未来薄 Python contracts adapter 与 Python Runtime 的潜在复用。若这些前提没有形成可验证 revision，则保持语言中立，不创建框架或根依赖。

### 11.3 预留路径与职责

```text
apps/digital-employee/
  web/
    src/product-shell/          # 侧栏、会话、连接与固定布局
    src/run-projection/         # 权威 snapshot/events 的只读 UI 映射
    src/node-interactions/      # 节点输入、Action、stop/reset/retry 入口
    src/memory-settings/        # 条件批准的长期记忆控制
  bff/
    application/                # 产品用例编排，不保存 Runtime 状态机
    ingress/                    # 可信 userId/环境、授权和版本 admission
    ports/runtime/              # 唯一 Runtime consumer port
    adapters/postgresql/        # 产品会话、投影和偏好元数据
    tests/contracts/            # named contract consumer tests

packages/a2ui-host/
  src/catalog-support/          # profile/catalog/digest/renderer 支持声明
  src/surface-projection/       # snapshot/update、sequence 与 gap
  src/actions/                  # node-bound Action envelope，不判业务成功
  src/components/               # 本地受信 React 组件
  tests/contracts/              # provisional fixtures 与 named revision 用例
```

目录名描述职责，不预先锁定 Python/TypeScript 包布局。根 `pyproject`、lockfile、workspace 和版本依赖只由 main-brain 协调修改。

### 11.4 Runtime/A2UI 复用边界

- contracts named revision 后，BFF 的 `ports/runtime/` 只映射 start/read/subscribe、节点 input/Action、stop、fresh reset 和 A2UI retry；不创建第二套运行命令或事件。
- 产品 PostgreSQL 只保存会话、关联、可重建投影和可选偏好；run/checkpoint/sequence/Action/stop 仍以 Runtime 为权威。
- Host contract tests 可直接复用 provisional DISPLAY_ONLY/INTERACTIVE fixture 的行为断言，但字段绑定必须等待获批 revision。
- 本轮已运行 fixture validator 的 14 个测试和 2 个合成 Application 校验；该结果只证明独立 fixture 规则，不证明 Host、BFF 或 Runtime 已实现。
