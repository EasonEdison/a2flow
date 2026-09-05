# 实现任务

> 本 change 仅完成设计。以下全部为未开始的实现任务；未获主控批准前不得执行。

## 1. 合约定版

- [ ] 1.1 接收并锁定共享 Asset/Release/Auth/Correlation 合约。
- [ ] 1.2 与 Runtime 定版 Start、snapshot/events、interrupt/resume、retry 和错误模型。
- [ ] 1.3 与 A2UI 组合端定版协议版本、catalog/artifact 身份、surface update 和 action 回传。
- [ ] 1.4 与 Capability Registry 定版演示待办 Adapter 的输入、输出、授权和幂等约束。

## 2. PostgreSQL 产品模型

- [ ] 2.1 实现用户会话、工作单和 Runtime 关联模型及迁移。
- [ ] 2.2 实现演示待办、发布回执和副作用幂等唯一约束。
- [ ] 2.3 验证 PostgreSQL-only 配置，不提供 MySQL、SQLite 或内存持久化 fallback。

## 3. 数字员工产品后端

- [ ] 3.1 实现创建工作单与重复请求幂等处理。
- [ ] 3.2 实现 Runtime Client Adapter 和可重建产品读模型。
- [ ] 3.3 实现读取工作单聚合视图、提交人工决定与显式重试入口。
- [ ] 3.4 实现会议纪要输入校验、业务文案与结果聚合。
- [ ] 3.5 实现演示待办 Capability Adapter 和授权复核。

## 4. React 产品体验

- [ ] 4.1 实现会话列表、工作单页、连接状态和安全错误入口。
- [ ] 4.2 实现可复用 A2UI Web Host 与受信 catalog registry。
- [ ] 4.3 实现 snapshot/update 收敛、cursor gap 检测和刷新恢复。
- [ ] 4.4 实现人工确认、并发冲突、失败重试和结果回执体验。
- [ ] 4.5 验证键盘操作、焦点恢复、屏幕阅读语义和移动端基本布局。

## 5. 验证与演示

- [ ] 5.1 编写产品 API、Runtime consumer 和 A2UI Host 契约测试。
- [ ] 5.2 验证未知版本/catalog/action fail closed，且不执行任意代码。
- [ ] 5.3 验证断线补 snapshot、重复/乱序事件和命令幂等。
- [ ] 5.4 验证 Adapter 响应丢失后的重试不重复写入。
- [ ] 5.5 用至少两个 API/worker 实例验证并发确认和实例切换。
- [ ] 5.6 执行端到端合成数据回归并记录字段级证据。
- [ ] 5.7 建立公开演示、三分钟路径和运行可观测证据。

## 6. 准出

- [ ] 6.1 主控批准设计和三项跨域裁决。
- [ ] 6.2 所有必需自动化验证通过并写入 `regression.md`。
- [ ] 6.3 部署和真实运行证据通过后更新 `readiness.md`；此前保持 `NO READY`。
