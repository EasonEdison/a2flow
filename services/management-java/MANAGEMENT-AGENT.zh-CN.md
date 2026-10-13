# 全局管理 Agent Java 边界

新入口独立于仍暂停的旧 `/chat` 和资产内 Java AI 入口。管理逻辑继续使用现有 dispatcher、授权、草稿并发和发布服务，Python 只负责 Deep Agents 编排。

## HTTP 与内部传输

- 四个 POST JSON 入口：`/api/management/v2/agent/conversations/create|list|read|send`。
- Cookie、浏览器 Origin 和管理员权限在入口校验一次。公开请求不接身份、角色、namespace、environment 或 grant。
- `create` 接 `requestId,title?`；`list` 接 `pageToken?,limit?`；`read` 接 `conversationId,afterEventSeq?,limit?`；`send` 接 `conversationId,requestId,message`。
- 成功 envelope 为 `{result:1,data:object,traceId}`，错误为 `{result:0,errorCode,errorMsg,traceId}`。时间为 ISO8601 字符串，事件 sequence 为 JSON 整数。Send 快速返回持久化 turn，随后 Read 分页轮询；Read 的 canSend/mutationsBlocked 是后端能力。
- Proto 位于 `proto/a2flow/management/v1/management_agent.proto`。Java 到 Python 使用显式 `A2FLOW_MANAGEMENT_AGENT_TARGET=127.0.0.1:<port>`，不自动重试。未配置时仅新入口明确返回 unavailable，旧管理入口不受影响。
- Python 工具回调注册到既有 Runtime gRPC listener，保留部署的 mTLS 配置。回调只接受 Java 签发的随机 grant；模型不能提供身份。grant 绑定 principal、namespace、conversation、父 requestId 和 PRT，30 分钟到期、容量 2048。重启失效明确报错，不用 Cookie 重新认证工具。
- Python 的单轮总时限不得超过 grant 期限；Java 超时/网络失败不能被前端当作确定未受理。未知结果先查历史/回执。

## 工具与发布

`ManagementToolCatalog` 是唯一 Agent 工具白名单。不开放 ONLINE、灰度、回滚、负责人替换、删除、写业务执行、任意网络目标或旧 coding 入口。`AUTHORING_CONTRACT` 返回实际能力 canonical 默认结构、当前 Workflow Schema、Skill bindings 合同和发布顺序；完整 A2UI 示例通过既有只读 blueprint import 返回。

能力仅通过 `CAPABILITY_DRAFT_CREATE_FROM_REGISTERED` 服务端复制已发布合同和 `CAPABILITY_DRAFT_UPDATE_METADATA` 保留合同的元信息更新；Agent 不开放完整 create/save，手工 API 不变。actionCode 在调用创建服务前按既有点分正则校验。能力 create/save/PRT deploy 还经过 `ManagementCapabilityGuard`：执行 binding（包括 descriptor、target 和 mappings）与 sideEffectLevel 必须匹配已有 PRT 发布快照。HTTP/未知 target 字段继续由现有 GRPC binding validator 拒绝。此额外限定只作用于新 Agent，不改手工管理端注册规则。

`CAPABILITY_DRY_RUN_READ_ONLY` 是真实预发验证的薄入口：只接受 draftId/revision/clientType，固定 PRT，服务端要求精确 revision、READ 副作用等级和已注册接口合同。原 dry-run 使用保存的 inputExampleJson、可信身份执行真实 RPC，并记录与当前 digest 绑定的证据。请求失败或内层 toolResult.success=false 均不算验证通过；失败证据仍由原服务保存。Agent 回执仅保留验证状态与安全统计，不持久化瞬时请求或业务响应正文。

四类资产使用现有 `RELEASE_OVERVIEW → RELEASE_CHANGE_CREATE（需要时）→ RELEASE_PREPROD_DEPLOY → RELEASE_DEPLOYMENT_DETAIL + RELEASE_OVERVIEW`，保留真实编译和依赖门禁。原 `CAPABILITY_PUBLISH` 与无冻结材料的 `PACKAGE_PUBLISH_PREPROD` 不开放。当前 native Workflow 仅支持 2–8 个线性 Skill 和一个 Summary；不静默丢弃其他执行语义。

Tool result 内的 `data` 为真实领域结果，`assets` 是浏览器安全投影。仅从 overview 的真实 PRT 指针产生 `publication.status=EFFECTIVE`；方法调用成功、校验通过和草稿存在不等于发布生效。业务数据执行成功更不在此边界内。

## 回执和显式迁移

由部署者以管理数据库 owner 执行 `backend/storage/db/migration/V002__management_agent_tool_receipts.sql`，服务不会自动建表。只创建 `management_agent_tool_receipt`，不修改旧表或引入任务调度域。

每个 mutation 先持久化 CLAIMED，再通过现有事务执行 dispatcher；正常管理结果与最终回执一同提交。唯一键包含 namespace/userId/conversationId/requestId，参数摘要冲突拒绝。相同请求返回已存结果，不重复执行。失去进程执行状态的 CLAIMED 及跨运行库发布的不确定结果返回 UNKNOWN，不自动重试。ReadReceipt 只能查询同授权用户与会话；新 grant 可以读取同会话旧请求的回执。发布存在跨库提交，不能用管理事务回滚宣称运行材料未写入。

## 构建和验证边界

使用 JDK 17 在 Mac 导出目录运行 `mvn -Dmaven.test.skip=true package dependency:copy-dependencies -DincludeScope=runtime`。不在低内存 ECS 编译，不运行单测。部署使用 classes + dependency，pom 未增加依赖。编译与本地无数据协议探针不代表真实资产已创建/发布，实际 Cookie、持久回执及四资产 PRT 链路由集成环境验收。
