# 验证记录

## 源码及适配器

2026-10-07：具名消息 DTO、Cron、Streams 的 Python 3.11 strict mypy/Ruff 通过；调度实现九个模块 strict mypy/Ruff/compile 通过。独立 Redis Unix socket 的发送、claim/reclaim、ACK 删除通过；真实隔离 PostgreSQL/Redis/HTTP smoke 通过。前端 TypeScript/Vite build 通过。用户免除单测，本轮未以完整单测或全站回归作为已通过项。

进度桥接的 Python lint/type 存在与基线相同的诊断，未扩大范围处理；新增路径未增加诊断。SSE 上游最多 60 秒 lease，不能承诺客户端断开即刻释放上游连接。

## 真实运行

测试工作流 `reading-creation-cron-demo`：阅读材料与确认 → 选择创作选题 → 生成并确认稿件。输入为自写技术验收材料，无真实联系人或外部发布。

- 实际 Cron：`* * * * *`，Asia/Shanghai；第三轮于 2026-10-07 05:08 UTC 触发，触发后停用。
- controlId：`0a96c96d-5d24-5e1d-9d98-e9f8fd7fce78`。
- runId：`bac80de457a0480fa5830da2b0c73fe0`。
- 模型/业务 RPC 生成三个真实 A2UI 卡片。第二、三轮因浏览器输入阻塞，使用同一部署的运行接口提交测试确认，不冒称 UI 点击验收。
- 第三轮三个节点均 SUCCEEDED，三个业务确认已保存；只生成草稿，未执行导出或外部发布。
- 启动 + 三个 resume + 三个 waiting 通知 + 完成通知，共八条 outbox 全部 completed。
- 两条曾因状态查询被拦截而 UNKNOWN 的恢复消息，在查询修复后由已有只读对账收敛，无 Action 或模型重放。

## 公网认证回读

使用已授权账号，经正常 `/api/auth/login` 登录，凭据和 cookie 仅存在内存，未写入源码或文档：

- `/api/runs/{controlId}`：SUCCEEDED，三个节点全部 SUCCEEDED。
- `/api/runs/{controlId}/cards`：三个历史快照均 DISPLAY_ONLY，完成运行不再开放操作。
- `/api/notifications`：完成通知 refId 为可访问的 controlId，不是错误的 native runId。
- `/api/runs/{controlId}/progress?limit=100` 与节点 history：返回实际已持久化执行记录。
- query guard 的定向 ASGI probe：正常状态/进度查询通过，缺少内部 token 401，未知/重复 query 400，无关接口仍拒绝 query。

## 本轮修复

1. ActionRequest 统一使用 from_mapping，避免非 canonical 中文 JSON 无法往返。
2. 节点提示明确整体目标不是跨节点授权；Skill 成功后返回，后继由 Workflow 调度。保留原应用权限与 Finalizer，不把业务场景写入引擎。
3. B 查询白名单只放行指定 status/progress 路径的声明参数，修复 UNKNOWN 对账与执行详情读取。

## 部署与资源

B 镜像 `cron-streams-493888d`；Runtime `cron-streams-32d57fe`；Scheduler `cron-streams-045f77a`。Redis 仅私有 Unix socket，无公开端口。Java、账号、业务执行、内容和 PostgreSQL 未重建。

一次实测 Redis RSS 约 8 MiB、消费者约 37 MiB；服务器 available 在本轮 508–598 MiB 间波动。不是固定容量保证。

## 浏览器门禁及收口

第一轮浏览器曾显示真实阅读卡片、选择及输入保留；最终版本尚未完成浏览器点击、刷新与视觉验收。旧标签停止确认后浏览器输入失效，新标签同样无点击效果，无 console 错误；已请求用户解除工具阻塞。HTTP/源码通过不代表此项通过。

2026-10-07 后续复验：新验收标签正常登录，工作流中心的我的运行显示一个已完成、两个已停止。打开上述已完成运行，三个节点与三张真实卡片均可见。阅读选择 rp-2/rp-3、补充意见、选题和稿件内容保留；确认按钮及输入框 isEnabled=false。历史过程展开包含 use_skill、execute_ability、query_skill_dependencies、render_application 的实际记录。三个节点结果收起后 aria-expanded 均为 false，卡片本身也可折叠。

刷新页面后，从通知中心的“工作流已完成 2026/10/7 13:11:26”再次进入同一完成运行，三节点、选择和内容恢复；页面刷新回到对话入口，未声称保留 Workflow 导航位置。定时管理显示 * * * * * / Asia/Shanghai / 已停用。此次只读取已有运行，未再次启动模型、提交 Action 或启用 Cron。浏览器 warn/error 记录为空。

截图：本地 /tmp/a2flow-cron-browser-accepted-20261007.png。本次范围 READY；不代表手机端、全站回归或最终运行三次 Action 均经 UI 点击。后续展示优化：摘要中英文混排，未导出稿件的提示措辞仍可改进。

## 后续三项收尾（2026-10-07）

### 完整页面交互

公网页面启动 control `c623013f281940189b1e0ee3126371dc` / run `7a11a11920144eebbd5cd7f1640d7167`，发现手动启动同步等待超过客户端十秒窗口；Runtime 继续生成卡片，但 B 在调用成功后才保存归属，造成孤儿运行。先只读确认实际身份及 control/run，再使用既有 repository 精确恢复该测试归属，未重新启动。

随后三个节点均经浏览器真实操作：阅读勾选 rp-2/rp-3 并填写补充意见；选题修改标题为“十分钟行动与次日复盘：职场新人的阅读实践”并确认；第三节点显示对应稿件并点击确认最终稿。三卡 COMPLETED 时间分别为 07:04:43、07:05:42、07:07:11 UTC；run SUCCEEDED。三个 resume、三个 waiting 通知和一个完成通知全部 completed，无错误。未导出、未对外发布。

### 手动启动修复及回归

手动入口先 reserve 归属，阻塞调用转 to_thread。仅 RUNTIME_UNREACHABLE 时只读查询一次同 control，确认 ID 与 runId 后返回原任务；不能确认则保留归属并报原错误。明确业务拒绝不查询、不重试。五场景 ASGI probe 覆盖正常、超时已受理、查询404、ID错配、容量拒绝；额外并发请求在慢启动期间仍可响应，POST 均仅一次。无新业务重试或降级。

源码 `4054211d83d7e3ad9465d4d6becfffa0da0b44af` 已推双远端，干净 main 构建，仅 B 更新至 image `cron-finish-4054211`。app.py 源码与镜像 SHA256 均 `516eab84876c167c5efd087c577bfb02b88f193afce865d08aa231a4c639019d`；前端 `index-B2LwdJwt.js`。Runtime、Redis、worker、数据库和 Java 未重建。

部署后页面再次启动验证：control `82cd0e250e12470c8a9fac80d6108de3` / run `59221c566a1b458b8777da8720b86cca`，归属于07:09:06 UTC创建，页面正常进入运行并于07:09:33看到首卡等待确认，无手工修复归属。达到启动验收目的后停止。浏览器停止确认工具超时且未返回可处理dialog，最后通过既有Runtime stop接口停止，刷新列表显示已停止；不冒称停止按钮UI验收通过。

### 隔离消息故障注入

实际隔离 PostgreSQL/Redis，独立消费者进程故障退出，下游为模拟HTTP接受记录器。Redis停机时PG pending保留，恢复后一次POST；收到entry后进程退出17，新consumer经XAUTOCLAIM回收；额外五次重复引用未新增POST；接受后退出23，通过隔离fixture时间快进触发UNKNOWN只读GET收敛，无POST重放。三条命令各一次POST、全部completed。测试容器及临时数据已清理，未停公网Redis/worker，未触碰旧UNKNOWN。此项证明投递和接受边界，不声称业务exactly-once或真实下游故障全覆盖。

### 展示回归

节点摘要不再截断展示模型英文/Markdown，改为状态中文和已有事件统计；最终结果仍完整保留。空下载内容提示“尚未生成下载内容”，禁用规则不变；非空但过时内容仍保留原校验。公网三节点中文摘要分别显示7/6/8次已记录工具调用，三节点结果与卡片可折叠，刷新回读成功，warn/error为空。桌面1280宽截图 `/tmp/a2flow-workflow-finish-20261007.png`。TypeScript/build、定向Python检查与diff检查通过；未跑完整单测、手机端或全站回归。
