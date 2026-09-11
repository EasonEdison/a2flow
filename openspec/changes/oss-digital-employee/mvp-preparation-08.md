# A2Flow 最小 B 端 MVP 准备方案

日期：2026-09-11。状态：PROPOSED；本轮只授权方案，源码路径以 AF-MVP-08 为准。
源码核对基线：origin/main b50d5a274be699fef7e0e569b6cdfeee6dd87f40；本任务合并 HEAD 9dd6462ee38741c03a588b4870ec03b92c1fdd56。
本增量覆盖旧 design.md 的会议纪要 fixture、全平台前置依赖及暂停口径；其他已确认行为继续有效。

## 1. 本轮边界

最小真实 MVP 使用 PostgreSQL 预置 Skill、能力、Application、Workflow，四个 M 编辑平台后置。演示暂沿用活动策划助手，仅生成方案及交互确认，不执行外部业务写。
界面保留对话主区与 Workflow 侧栏。侧栏显式启动预置 Workflow；主区呈现启动输入、节点过程、交互卡片与真实结果。
D2 节点补充输入仍为已确认产品需求，但本切片后置，不绘制假可用“补充一句”或聊天发送入口。普通对话自由聊天接口若未释放，也不以 Workflow start 冒充聊天。
刷新读取原 run 和卡片，不自动重跑。stop 接受后卡片只读，restart 显式创建全新 run，无旧上下文继承。
本轮未安装依赖、启动监听、调用 provider、连接数据库或部署。

## 2. 现有源码与精确缺口

- git ls-files 未发现 apps/、packages/a2ui-host/ 内源码或前端 package.json；现有 B 端是方案，没有应用实现。
- services/agent-workflow-runtime/src/agent_workflow_runtime/http.py 已有 start、control、inspect、Action、stop、restart。
- service.py 的 start/action/restart 同步等待执行后返回 snapshot；不能等待 start HTTP 完成才开始显示进度。control receipt 可用来获取 runId，分配前可能 404。
- projections.py 的 snapshot 只含 lifecycle、operationHistory、interactions 摘要。lifecycle 当前仅 RUNNING/STOPPED/SUCCEEDED；operation RETURNED 不是节点成功，nativeExecution 明示未证明活性。
- snapshot 的交互只有 nodeId、interactionId、recordedPhase、actionEligibility 等，没有 Application 组件树、输入 schema、actionName 或最终业务结果。刷新重建卡片不能仅靠此快照。
- progress_http.py 已有 catalog/history/stream；/events 仍是 snapshot，不能用作 SSE。AF07 源码存在不等于真实浏览器/PG/provider 联调通过。
- postgres_progress.py 返回 catalog 的 node_id/execution_id 等实际下划线字段；客户端边界显式映射，不机械改共享字段。
- 当前 create_app 要求可信宿主设置 scope['a2flow.trusted_context']，客户端自填 userId/header 不成立；身份与会话宿主、CSRF 和同源代理接线仍需明确。
- 当前路由未提供 Workflow catalog、普通聊天、用户会话/run 列表、完整节点成功/失败/跳过及最终结果投影、A2UI retry HTTP 入口。不能画可用按钮或由进度推断这些能力。

## 3. 最小工程与拥有路径提案

推荐 React + TypeScript + Vite 静态 SPA，普通 CSS；现有工程没有可复用前端脚手架。保留 Python 薄产品宿主，复用现有 FastAPI/RuntimeService 公开边界，由主控明确宿主 owner；不新增常驻 Node BFF、第二个执行调度器或数据库引擎。
Vite 官方 react-ts 模板可作为后续脚手架依据：https://vite.dev/guide/ 。具体版本、许可证、Node 兼容性、下载量及唯一 lock 位置在 AF-MVP-08 依赖窗口前核定；本轮不选择浮动 latest 或安装包。

拟申请（尚未释放）：
- apps/digital-employee/web/：页面壳、侧栏、启动输入、节点过程、API adapter、恢复逻辑、样式和前端构建配置。
- apps/digital-employee/bff/：若主控将薄宿主交本域，限会话/可信上下文接线与产品读投影；具体 endpoint 另定，不碰 Runtime 内部调度。
- packages/a2ui-host/：仅预置 Application 实际需要的可信组件与 Action 输出；不做完整通用编辑/插件系统。若 AF-MVP-08 选择先留 web 内组件，则以后抽包，不抢先创建双实现。
- 本轮实际拥有并修改：openspec/changes/oss-digital-employee/ 内本方案及自有 checkpoint。

依赖提案：运行时 react/react-dom；开发时 typescript、vite、@vitejs/plugin-react、React 类型。请求使用 fetch，SSE 优先同源 EventSource（身份方案确认后决定），单页 URL 使用原生 History API；暂不加入路由库、状态库、UI 全家桶或重复 Python HTTP 栈。
前端仅管理视图与订阅状态。测试阶段按已批准现有设施选取 reducer/接口边界和少量浏览器链路验证；不在本轮为文档安装测试工具。

## 4. 现有接口映射（消费事实，不发布新契约）

| 页面动作 | 现有接口/请求 | 处理与未决 |
| --- | --- | --- |
| 启动 | POST /runtime/runs；controlRequestId, definitionKey, inputs | 定义从可信预置 catalog 选择；输入 schema 待提供；先保存请求 ID，启动中查询 control |
| 查启动回执 | GET /runtime/controls/{control_id} | 使用 runId/delivery；DISPATCHING/UNCONFIRMED 不视为成功；404 暂未分配，不自动重发 start |
| 恢复/权威状态 | GET /runtime/runs/{run_id} | 使用 lifecycle/interactions；缺完整结果、节点终态和卡片内容，需最小产品投影 |
| 发现执行段 | GET /runtime/runs/{run_id}/progress?after=…&limit=… | 使用 segments、nextCursor、hasMore；不能复用 history cursor |
| 历史 | GET /runtime/runs/{run_id}/nodes/{node_id}/executions/{execution_id}/history | 按 seq 读 records、nextCursor、capture；只读展开 |
| 增量 | 同 execution 路径 /stream | progress/capture/capture_end/heartbeat/error；cursor 为 executionId:seq；after 与 Last-Event-ID 二选一 |
| 卡片 Action | POST /runtime/runs/{run_id}/nodes/{node_id}/actions；controlRequestId, interactionId, actionName, inputs | 仅由有效卡片 schema 构造，服务端再准入；HTTP 返回不等于业务成功 |
| 停止 | POST /runtime/runs/{run_id}/stop；controlRequestId | 收到 STOPPED 后只读；请求失败/未确认不伪造停止 |
| 全新重启 | POST /runtime/runs/{run_id}/restart；controlRequestId, inputs | 显式用户操作、新 run；现有服务限制来源，非 stopped 重启/reset 能力需 Runtime 明确 |
| 配置失配 | error.code=RESET_REQUIRED | 阻断操作并提示显式重置；未确认可重置接口前不调用不支持的 restart 来源 |

## 5. 展示与恢复

运行默认展开允许展示的 REASONING_DELTA/TEXT_DELTA，标注模型输出；工具与节点真实事件独立呈现。NODE_RETURNED、MODEL_RETURNED、sealed、capture_end 均不能当成业务成功或节点完成。
等待交互显示“等待你确认”，卡片继续可操作，不能因为模型流结束收起成已完成。真实终态到达后收起过程，保留摘要/结果/A2UI；无真实耗时/统计不显示。详情只查询保存记录。
URL 保存原 runId；未获得 runId 前保存本次 controlRequestId 以便刷新恢复查询。浏览器存储只作定位线索，可信服务端鉴权决定归属；换用户/环境隔离线索，不存凭据和原始内部响应。
刷新顺序：恢复可信会话 -> GET 原 run 或 control -> 获取产品卡片/结果投影 -> catalog -> history -> 从最后已处理 cursor 订阅。重复记录以 run/node/execution/seq 去重，跨执行不拼接。catalog 继续发现新段。
SSE 最多 60 秒 lease，服务端总订阅上限 8；采用有界退避重连和订阅预算，切换 run/卸载关闭订阅。具体最小 Workflow 并行数由预置资产确认；不擅自占满服务器名额。分页历史限制内存，无无限 DOM 累积。
PROGRESS_UNAVAILABLE/incomplete 只影响过程展示，保留明确提示并继续读权威状态；不自动重试业务调用。断开订阅只结束观察，不能 stop/restart run。

## 6. 请求 main-brain 协调的最小依赖

1. 预置活动策划 Workflow 的 definitionKey、节点顺序/名字、入口 inputs schema，以及 PG 持久化 catalog 的最小读取方式；不需要 M CRUD。
2. 可信用户/环境的宿主与会话入口、同源路由归属；UI 不构造 TrustedContext。自由对话是否进入本工程切片需明确接口，不能以普通文本隐式控制 Workflow。
3. 授权的节点/结果/Application 投影：完整有效卡片、actionName/input schema、实例关联、真实节点终态、最终结果和只读历史；上述字段目前不在 snapshot 中。
4. start pending 的 control 查询时机与未确认处理、RESET_REQUIRED 对应显式 reset 路径、restart 来源限制；仅确认本次实际暴露的按钮。
5. 发布 AF-MVP-08 的准确路径、最小组件集合、依赖/lock owner 和源码验证范围。

## 7. 后续准出（本轮未执行）

真实预置 PG 资产经可信服务启动 -> 长调用流式节点过程 -> A2UI 等待/提交 -> 真实结果；刷新保留同 run 与卡片；历史查看零执行；stop 后卡片禁发及后端拒绝；显式 restart 得到新 run；并行/执行段不串流；敏感信息不泄漏；D2 后置入口不出现。
源码构建/接口合成测试、真实 PG/provider/browser 证据、部署状态分别记录。当前 UI NO READY。
