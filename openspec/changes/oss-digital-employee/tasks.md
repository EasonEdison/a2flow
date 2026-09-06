# 实现任务

> Phase 1 已授权推进设计对齐；以下实现任务全部未开始。共享接口 owner 给出命名修订并由 main-brain 审查前，不得编写应用代码。

## 1. 合约定版

- [ ] 1.1 接收 contracts owner 的命名修订：可信主体/环境、不可变发布引用、请求去重、错误与关联语义。
- [ ] 1.2 定版 start/read/subscribe、节点 Action、stop、fresh reset、A2UI 节点 retry 和配置版本失配语义。
- [ ] 1.3 定版事件投影、run 顺序、snapshot 补偿，并确认产品不另建第二套 event/action schema。
- [ ] 1.4 定版 A2UI profile/catalog 支持声明、surface 身份、DISPLAY_ONLY/INTERACTIVE 和业务成功/完成交互的分离。

## 2. 最小产品 BFF

- [ ] 2.1 在 `apps/digital-employee/` 实现侧栏显式启动和受信 `userId`/环境注入。
- [ ] 2.2 实现 run 查询、事件投影、缺口补 snapshot 和节点绑定输入。
- [ ] 2.3 实现 Action、stop、fresh reset 与仅限 A2UI 所属节点的 retry 端口。
- [ ] 2.4 使用 PostgreSQL-only 产品状态；不提供 MySQL、SQLite 或内存持久化 fallback。
- [ ] 2.5 首片只使用合成 fixture，不实现真实业务写入或产品侧业务重试。

## 3. React 产品体验

- [ ] 3.1 在 `apps/digital-employee/` 实现固定产品壳、侧栏启动与 Workflow 选择。
- [ ] 3.2 实现运行节点卡、节点绑定输入和 DISPLAY_ONLY/INTERACTIVE 状态。
- [ ] 3.3 实现配置版本失配 reset 提示、stopped 历史卡只读和后端拒绝结果展示。
- [ ] 3.4 实现 A2UI 节点失败的显式 retry；非 A2UI 失败不展示 retry。

## 4. 可复用 A2UI Host

- [ ] 4.1 在 `packages/a2ui-host/` 实现受信 catalog/profile 协商与支持声明消费。
- [ ] 4.2 实现 snapshot/update 收敛、未知资产 fail closed 和本地组件渲染。
- [ ] 4.3 Action 只回传结构化意图，由 BFF 重新授权；Host 不推断业务成功或完成交互。
- [ ] 4.4 验证键盘操作、焦点恢复、屏幕阅读语义和移动端基本布局。

## 5. 可选的个人长期记忆控制

- [ ] 5.1 在接口放行后核验仓库的 PostgreSQL Store、namespace、delete 权限和 preference 现状，向 main-brain 提交 A/B/B+ 最小 diff 与成本。
- [ ] 5.2 经 main-brain 判定低成本后，实现设置页和当前用户 list/delete/preference；允许增加最小偏好元数据与薄 facade。
- [ ] 5.3 验证禁用长期记忆不影响当前聊天/run，删除记忆不删除聊天，且不能跨用户 namespace。
- [ ] 5.4 新索引、记忆正文 schema 改造、派生删除、上传/切块、共享、搜索或知识库 UI 不在本阶段。

## 6. 验证与准出

- [ ] 6.1 为 BFF consumer 与 A2UI Host 编写命名修订对应的契约测试。
- [ ] 6.2 验证 R1-R8，并在至少两个 BFF/worker 实例与 PostgreSQL 上记录字段级证据。
- [ ] 6.3 main-brain 批准设计和跨域裁决；接口 owner 的命名修订已集成。
- [ ] 6.4 部署和真实运行证据通过后更新 `readiness.md`；此前保持 `NO READY`。
