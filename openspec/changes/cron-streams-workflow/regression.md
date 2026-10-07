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
