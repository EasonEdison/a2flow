# Python 运行态迁移差异核对

核对基线：7a6a664，2026-09-23。用户确认仅 M 端 Java，其余 Python。本文件记录实际缺口，不修改已部署链路，也不将临时兼容误称为最终架构。

| 职责 | 当前代码 | 目标与验收 |
| --- | --- | --- |
| 模型/Skill 执行 | Python `services/agent-workflow-runtime` | 保留，不建立第二套 Agent |
| 内容业务 | 当前没有 | 新增 `services/content-service`，Python、PostgreSQL、既有 gRPC 身份契约 |
| 业务能力发布选择与执行 | Java `backend/capabilityrpc/PublishedCapabilityExecutionService.java`、`GrpcCapabilityTransport.java` | 在 Python 执行侧保持同环境发布选择、版本比对、参数映射、响应校验和下游 gRPC；禁止直读草稿或静默换版本 |
| A2UI 展示/Load/Action | Java `backend/a2ui/runtime/A2uiRuntimeFacade.java` | Python 解释同一已发布契约，保留显示更新、可信 session、Action 结果与完成语义 |
| 卡片持久化与 Chat 接入 | Python `chat/rpc_assets.py`、`chat/rpc_actions.py` | 复用原卡片/消息记录，RPC 接口可保持，不能把浏览器私有快照当真值 |
| M 编辑/编译/发布 | Java 管理服务 | 保留 Java；编译材料与发布事实需供 Python 读取，管理服务不执行用户业务 |

## 顺序

1. 先提交独立 Python 内容业务内核和明确 gRPC 合同，验证真实数据库与业务权限。
2. 迁移通用能力执行，再迁移 A2UI 确定性解释；复用已有契约与行为证据，不重设计产品。
3. 同一组合同样例验证 Python 行为，包括拒绝路径，再将引擎目标切至 Python 服务。
4. 通过真实 M 页面建立本场景资产，先独立 Chat 后三节点 Workflow，最后公网部署验收。

仅有 Python 内容服务不代表第 2、3 步已经完成。不把业务特定逻辑塞进通用执行服务来缩短接入，不因迁移增加 HTTP 业务降级。

## 本批不改变的线上事实

线上仍可能调用 Java 确定性运行态。源码/隔离服务验证通过后仍需单独部署和用户页面验收；在该证据完成前不宣称“除 M 外已全部 Python”。
