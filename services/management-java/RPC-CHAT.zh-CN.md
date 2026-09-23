# 业务能力与 A2UI 的 Chat 执行链

本轮只接通手填管理端与普通 Chat。Workflow 编排、节点推进、M 端 AI 辅助生成均不在本轮范围。

## 职责

- Java 管理端：维护组件 Catalog、Application、业务能力、Skill 及通用资产关系，编译和发布不可变配置。
- Java 确定性执行服务：解释已发布能力的输入映射，通过 gRPC 调用下游，按已发布 Application 执行 Show、Load、Action、结果分支和界面更新。不运行模型循环。
- Python Deep Agents：从环境数据库恢复 Skill 文件结构，通过 `use_skill` 准入，再调用 `execute_ability`、`render_application`。管理对话、消息、卡片及 Action 幂等记录。
- B 前端：使用官方 A2UI React renderer 呈现嵌套组件与数据绑定，提交本卡片声明的 Action context。浏览器不能指定业务地址、服务身份或私有运行快照。

## 两段 RPC

引擎到 Java、Java 到业务下游均为 Protobuf gRPC；业务请求不转发 Cookie。`userId` 使用带 presence 的 signed int64，来自已验证的服务端会话。管理页面和账号登录仍是 HTTP；发布桥是控制面 HTTP，不是业务执行兜底。

通道支持 mTLS；只有显式本机测试配置允许 loopback 明文。Java 当前固定监听 127.0.0.1，生产跨机拓扑还需明确受控网络入口，不能仅设置 mTLS 就认为跨主机部署完成。[RPC 配置说明](backend/capabilityrpc/README.zh-CN.md)列出证书与目标映射。地址、证书来自宿主配置，不放入模型参数。超时不自动重试，不推断下游是否已经产生副作用。

能力的公开 `actionCode` 与管理发布实体 `draftId` 不同。模型和 A2UI 使用 actionCode，已发布映射转换为唯一实体后执行；不得读取当前草稿猜测身份。

## 发布与读取

PRT 与 ONLINE 的 Runtime 材料写入不同数据库。完整 Java 编译 payload 原文、sourceId 与摘要一并保留，未知扩展字段不裁剪。

Java 发布状态是 Ability/Application 的唯一生效选择来源，包括 ONLINE stable/gray 与 userId 灰度。Python 的库存索引不能替代此选择：每次解析先通过 RPC 获取当前发布身份，再匹配同环境数据库中的留存材料。缺失、重复、摘要不一致均报错，不读取草稿、不跨环境、不选最新版本兜底。

Skill 仍通过既有 DB 材料端口恢复。准入时向模型提供绑定能力的业务参数契约和 Application 参数契约，不暴露 gRPC 目标、descriptor、私有 session 或凭据。

## 卡片生命周期

1. `render_application` 验证 Skill 绑定及当前依赖版本，Java Activate 再验证 Application sourceId/digest，随后执行 Show 和有序 Load。
2. Python 将完整 snapshot、允许的 Action、私有 session 和 Skill 版本闭包持久化。INTERACTIVE 等待操作；DISPLAY_ONLY 不暂停，但允许配置中的普通 Action。
3. 浏览器提交 cardId、requestId、revision 和 surface/component/action/context；后端从数据库读取可信卡片，不接受浏览器提供的 session、Build、userId 或完整快照。
4. 数据库先原子 claim，提交事务后调用 RPC；完成后同一事务写卡片快照、私有运行状态、结果和幂等回执。网络调用不占有数据库事务。
5. 同 requestId 同载荷重放已保存回执；不同载荷冲突。未知执行结果锁定，不自动重试。刷新只读持久状态，不重新执行。

Application 发布变化在业务调用前返回 `RESET_REQUIRED`，提示重新开始；不解释旧卡片为新配置。Skill 依赖版本在入口核对，不提供跨所有资产的分布式快照事务。claim 后进程崩溃的自动恢复器未实现，不能把未知业务操作当作未执行。

## 渲染范围与验证

基础 Catalog 使用官方明确 ID，扩展 Markdown 使用独立 Catalog。只注册实际有渲染实现的组件；未知 Catalog/自定义组件显式报错。组件中心的注册和编译校验不能代替 B 端渲染实现。

可复跑的验证：

- `tests/host/run-local.sh`：独立 PostgreSQL、账号会话与真实管理宿主启动。
- `backend/storage/db/tests/run-capability-rpc-probe.sh`：真实双段 gRPC、发布读取、精度、环境与错误边界。
- `publication-bridge/run-local-tests.sh`：PRT/ONLINE 数据库发布、依赖闭包、完整材料留存和原子回执。
- `tests/runtime/run-chat-rpc-integration.sh` 与 Python `deploy.attended.verify_rpc_chat`：通过真实 M 接口创建与发布，再验证 Chat 卡片持久化链。

源码、隔离联调、生产证书验收和公网部署是不同交付状态。以最终验证记录为准，不以文件存在或单项构建通过代替整链验收。

### 2026-09-23 隔离整链结果

通过真实管理 HTTP 创建、绑定并发布 Ability、官方 18 组件 Catalog、含 LoadBinding / ActionBinding 的 Application 和 Skill。随后 Python 从 PostgreSQL 恢复 Skill，经实际两段 gRPC 执行业务，精确核对直接能力输出、Load 后快照与 Action 后快照的业务返回值。Action 完成、同请求重放、重新建立卡片仓库后逐字恢复、其他用户隔离、已完成卡片拒绝第二次操作均通过。

卡片合约 14 项通过（7 项真实 PostgreSQL、7 项内存）；RPC 客户端 5 项真实 loopback 检查通过；Java 发布选择到 Python 留存材料的 5 项检查通过。4 个新增 Runtime 接入文件 strict mypy 通过。原有 Chat 回归 44 项中 31 通过、13 条件数据库项跳过，其中卡片 7 项数据库检查已在上述独立命令补跑。

联调发现并修复可选空 `successBranches` 经序列化省略后为 null 的兼容问题；修复遵循原“无分支配置”语义。失败时业务结果未知的旧卡没有自动重试，修复后使用全新卡片验证。

这里的业务下游是本项目合成 gRPC 服务，管理会话是隔离数据库测试会话；没有调用真实模型、生产业务或部署公网。该结果证明配置到执行与持久化链路，不证明生产接入已完成。

B 端在本地生产构建预览中使用上述实际持久化卡片的公开 JSON 检查：Load 返回值可见、点击事件 context 与声明匹配、完成卡只读、刷新保留结果，桌面页面无控制台错误。该浏览器检查使用公开卡片 HTTP 夹具，不重复业务操作，也不是公网站点验收。
