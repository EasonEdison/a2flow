# 回归计划

## 证据状态

- 状态：`PLANNED`
- 已执行自动化：无
- 已执行端到端：无
- 已执行部署验证：无
- Runtime：`NO READY`

## 已执行的跨域辅助验证

- 命令：`node --test packages/a2ui-contract-fixtures/test/validate-fixtures.test.mjs`。
- 结果：14/14 测试通过；独立 validator 同时验证 2 个合成 Application fixture。
- 边界：只证明 provisional fixture 的 DISPLAY_ONLY/INTERACTIVE、版本 admission、retry allowlist 和 Finalizer 规则；不证明本 change 的 Host、BFF、Runtime 或 named contract 已实现。

下列 operation、params 和 `data` 是待 contracts owner 命名修订的消费语义，不冻结公开 method 或字段名。

## R1 侧栏显式启动与可信上下文

- operation：start-run（语义占位）。
- 触发：用户从侧栏选择 Workflow 与 PRT 或 ONLINE 后显式启动；普通聊天消息作为对照。
- params：服务端注入的 `userId`、环境、不可变 Workflow 发布引用、请求去重标识；客户端主体/环境覆盖作为非法输入。
- 期望成功 data：run 身份、接受的发布引用、环境、起始 revision。
- 字段断言：只有侧栏操作启动 run；普通聊天不启动；相同请求不重复启动；客户端不能伪造主体或环境；PRT 不解析 ONLINE 灰度。
- 证据：`PLANNED`。

## R2 有序事件、重放与缺口补快照

- operation：subscribe-run-events / read-run（语义占位）。
- 触发：两个 BFF 实例先后消费重复、倒序事件，断线后从最后连续 run sequence 继续，并模拟 gap。
- params：run 身份、最后连续 sequence、可信授权上下文。
- 期望成功 data：snapshot revision、接受的 sequence、事件列表、surface 列表。
- 字段断言：run 投影按单 run sequence 排序去重；公共事件外壳单独按其稳定身份去重；gap 后 delta 不应用，先取权威 snapshot。
- 证据：`PLANNED`。

## R3 节点绑定输入

- operation：submit-node-input（语义占位）。
- 触发：Workflow 节点等待用户输入；分别从目标节点卡和普通聊天提交相同文本。
- params：run/node 关联、所见 revision、结构化输入、可信主体。
- 期望成功 data：接受的节点、下一 revision、权威节点状态。
- 字段断言：只有目标节点入口推进节点；普通聊天不被解释为 resume；错误节点、主体或过期 revision 被类型化拒绝。
- 证据：`PLANNED`。

## R4 A2UI 显示、交互与结果事实

- operation：render-surface / submit-action（语义占位）。
- 触发：先呈现 DISPLAY_ONLY surface，再呈现 INTERACTIVE surface，并提交成功与失败两种 Action 结果。
- params：获批 profile/catalog、surface 与来源节点关联、结构化 Action、所见 revision。
- 期望成功 data：已应用 surface sequence、Action 权威结果、业务成功事实、是否完成本次交互。
- 字段断言：DISPLAY_ONLY 不暂停 Workflow；INTERACTIVE 等待 Action；业务成功和完成交互是两个独立事实；Finalizer 不能覆盖 Tool/Action 事实；未知资产 fail closed。
- 证据：`PLANNED`。

## R5 配置版本失配与 fresh reset

- operation：continue/action/reset（语义占位）。
- 触发：run 创建后变更轻量配置有效版本，再尝试 continue 与 Action，最后由用户显式 reset。
- params：run/node、所见 revision、当前有效配置版本、reset 请求去重标识。
- 期望错误/成功 data：类型化配置失配及 reset 提示；随后返回全新 run 身份与新发布引用。
- 字段断言：失配入口不做新工作；不继续旧配置、不静默迁移、不自动重启；新 run 不继承旧 context/checkpoint/results/interactions，也不检查旧业务结果。
- 证据：`PLANNED`。

## R6 stop、迟到结果与历史卡只读

- operation：stop-run 及其他控制操作（语义占位）。
- 触发：多分支 run 工作中提交 stop；随后送达迟到结果，并在历史卡尝试 Action、输入、retry 与 continue。
- params：run 身份、所见 revision、控制请求去重标识、可信主体。
- 期望成功/错误 data：stopped 权威状态、迟到事实记录、后续操作的类型化拒绝。
- 字段断言：所有分支不再开始新工作；迟到结果只作为事实；历史卡只读；stopped run 不可 resume。
- 证据：`PLANNED`。

## R7 retry 与业务幂等责任边界

- operation：retry-a2ui-node / execute-ability（语义占位）。
- 触发：分别制造 A2UI 渲染失败、Action 失败/结果不满足配置成功、Skill/model/非 A2UI Tool 失败和业务 API 暂时失败。
- params：失败所属节点、权威结果、配置成功条件、可信主体。
- 期望成功/错误 data：仅 A2UI 所属节点出现显式 retry 资格；其余失败只返回事实。
- 字段断言：不存在通用 Workflow retry；业务重试与幂等由被调 API 后端决定；产品/Runtime 不查询旧业务结果、不补偿、不跨 run 去重。
- 证据：`PLANNED`。

## R8 可选的个人长期记忆控制

- operation：list-memory / delete-memory / set-memory-preference（语义占位，仅在低成本前提成立时）。
- 触发：当前用户分页查看并删除一条记忆，随后关闭长期记忆并继续当前聊天。
- params：服务端可信 `userId`、分页游标或记忆 key、禁用偏好。
- 期望成功 data：当前用户记忆摘要、删除确认、禁用状态。
- 字段断言：不可访问其他用户 namespace；删除记忆不删除聊天；禁用后停止长期读/新写，但当前聊天、当前 run 和短期上下文继续。
- 证据：`PLANNED`；若需要新索引/schema、删除传播或知识库能力则本用例延期。

## 计划环境

- 合成数据，不连接真实办公系统，也不执行真实业务写入。
- PostgreSQL 是唯一关系型数据库；不启用 MySQL、SQLite 或内存 fallback。
- 多实例门禁至少包含两个无状态 BFF/worker 实例和共享 PostgreSQL。
- 精确 Runtime/A2UI 版本、接口命名、实现、测试和部署均未完成，因此本文件不能作为 runtime 可用证据。
