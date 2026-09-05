# 业务能力注册平台提案

## 状态

- 设计状态：PROPOSED
- 源码范围：仅设计文档
- Runtime 状态：NO READY
- 审批状态：等待 main-brain 统一裁决

## 为什么要做

M 侧需要一种可发布、可验证、可被通用 Runtime 消费的业务能力契约。它必须描述“能力能接收什么、返回什么、哪些输入可由模型生成、哪些是固定常量、哪些只能来自可信运行上下文”，同时不能把业务实现、密钥或企业 API 平台耦合进 Runtime。

如果直接把任意 HTTP 接口或模型生成的参数交给 Runtime，会混淆定义期与执行期职责，也会让调用方有机会伪造租户、身份等可信字段。本 change 用一个小而完整的契约切片解决这一边界。

## 目标

- 定义业务能力草稿及不可变已发布契约。
- 用 JSON Schema 描述模型参数、最终调用输入和调用输出。
- 用显式绑定规则分离 `MODEL_ARGUMENT`、`STATIC_CONSTANT`、`TRUSTED_CONTEXT` 三种来源。
- 定义 Runtime 读取发布契约和调用适配器的逻辑端口。
- 只存储凭证需求与不透明 `CredentialRef`，不存储或返回凭证明文。
- 规定发布前静态验证、并发冲突、失败分类和重试安全边界。
- 保持 PostgreSQL-only、多实例应用下的一致性。

## 非目标

- 不实现真实业务适配器、HTTP 客户端、模型调用、Runtime 或前端。
- 不依赖企业 API 平台、企业协议、内部 schema 或私有数据。
- 不在本 change 决定 Runtime 语言、HTTP/gRPC/消息协议或其版本。
- 不实现通用低代码 API 编排、凭证中心、组织/租户管理或任意脚本执行。
- 不发布服务、不修改数据库、不开放端口。

## 候选方案

| 方案 | 描述 | 优点 | 主要代价 |
| --- | --- | --- | --- |
| A. OpenAPI 导入优先 | 以 OpenAPI Operation 作为能力主模型 | HTTP 工具链成熟，已有 API 容易导入 | 将首版模型绑定到 HTTP；常量、可信上下文和凭证边界需要额外扩展；非 HTTP 适配器不自然 |
| B. SDK/协议优先 | 先冻结某种语言接口或 RPC IDL | 强类型生成和调用性能好 | Runtime 语言与传输协议尚未裁决，过早冻结会制造跨任务冲突 |
| **C. 契约优先（推荐）** | 以 JSON Schema 2020-12 + 来源绑定 + 逻辑端口表达能力，传输绑定后置 | 可静态验证、语言中立、适配器可替换，最符合当前待裁决状态 | 后续需要为选定传输补充映射与兼容性测试 |

## 推荐方案

采用方案 C。能力注册平台拥有“定义、验证、发布、查询”的控制面；Runtime 只读取不可变发布契约，并通过逻辑 `CapabilityInvocationPort` 调用外部适配器。OpenAPI 可在后续成为导入格式或某类适配器描述，但不是领域真值。

首版只支持 JSON 值，schema 候选方言为 JSON Schema Draft 2020-12；`inputBindings` 使用 RFC 6901 JSON Pointer 指向最终输入位置。发布产物必须自包含，MVP 禁止运行时解析任意远程 `$ref`。

## 预期产物

- 可并发编辑、显式校验的 `CapabilityDraft`。
- 包含内容摘要的不可变 `PublishedCapabilityContract`。
- Runtime 使用的 `PublishedCapabilityCatalogPort` 和 `CapabilityInvocationPort` 逻辑契约。
- 7 类发布门禁和 8 个 planned 验收场景。
- 对共享资产标识、发布语义、可信上下文目录和 Runtime 传输映射的明确依赖。

## 跨域影响

| 依赖方 | 本域输出 | 本域所需输入 |
| --- | --- | --- |
| oss-platform-contracts | 能力领域 payload、发布校验结果、内容摘要候选 | `AssetIdentity`、`ReleaseRef`、不可变发布与错误包络 |
| oss-agent-workflow-runtime | 发布契约读取端口、调用端口、失败/重试语义 | 传输映射、执行上下文真实性、deadline 与幂等策略 |
| oss-skill-registry / oss-workflow-composer | 稳定能力发布引用 | 共同引用格式和兼容性规则 |
| oss-digital-employee | 凭证槽位和适配器实现边界 | 业务适配器、环境凭证绑定；不得把业务模型反向放入 Runtime |

## 风险

- JSON Schema 实现之间的 `format`、浮点数和远程引用行为可能不一致，必须固定方言、验证器能力集和兼容性用例。
- 超时后副作用状态可能未知，不能把“网络失败”等同于“未执行”。
- `CredentialRef` 若被错误地当作普通模型参数传递，会破坏可信边界。
- 公共发布语义未统一前，本域只能提交 PROPOSED 草案，不能宣称跨域契约已批准。

## 公开规范依据

- JSON Schema Draft 2020-12：<https://json-schema.org/draft/2020-12>
- RFC 6901 JSON Pointer：<https://www.rfc-editor.org/rfc/rfc6901>
- OpenAPI 3.1.1（候选方案对比）：<https://spec.openapis.org/oas/v3.1.1.html>
- RFC 9457 Problem Details（仅作为未来 HTTP 映射参考）：<https://www.rfc-editor.org/rfc/rfc9457.html>
