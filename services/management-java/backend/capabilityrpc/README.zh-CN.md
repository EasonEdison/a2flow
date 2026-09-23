# 能力双段 gRPC 执行

执行链是引擎 → `CapabilityExecution.Resolve/Execute` → Java 已发布能力解析/映射/校验 → 业务服务已注册 unary gRPC 方法。两段均为 HTTP/2 上的 Protobuf gRPC，不是 HTTP JSON 业务调用。管理端浏览器 HTTP API 不变，Workflow 不在本实现范围。

## 注册合同

`supportedClients` 与 `clientVariants` 的 PC/APP/COMMON 规则不变。每个 variant：

- `apiSource.sourceType = GRPC`。
- `executionBinding.bindingType = GRPC`。
- `executionBinding.target` 只接受 `targetKey`、`serviceName`（完整包名）、`methodName`、`descriptorSetBase64`、`contextField`。
- `descriptorSetBase64` 是 `protoc --include_imports --descriptor_set_out=...` 生成的 FileDescriptorSet 编码。业务请求必须包含名为 contextField 的 `a2flow.capability.v1.ExecutionContext` 单消息字段，导入项目 `proto/a2flow/capability/v1/capability.proto`。平台上下文描述必须一致，不允许自定义同名身份结构。
- 保留原 `modelContract.inputFields` 三种来源、`requestMappingsJson` 与确定性系统变量映射。业务映射不能写 contextField；身份仅由宿主注入。Cookie、headers、URL、HTTP method/authMode 等旧字段拒绝，不迁移、不降级。
- `timeoutMs` 为 1..120000；`maxResponseBytes` 最多 5MiB；`idempotency=NONE`，不自动重试；`responsePolicy=ORIGINAL`。
- 返回值遵循 ProtoJSON：int64 是十进制字符串，作者 responseDemoJson 必须据此填写。继续由原 Demo/字段规则生成 `technicalOutputSchema`，真正返回值用 NetworkNT JSON Schema 校验。外部 schema 引用禁止。

首次中文名注册仍只提交 payloadType/mode/basicInfo.nameCn，完整技术字段在后续保存。

## 第一段与发布身份

协议：`proto/a2flow/capability/v1/capability.proto`。`asset_key` 是能力 draftId，不是 actionCode。Resolve 通过原 `CapabilityActionToolProvider → EnvironmentAwareAssetResolver → AssetReleaseStateRepository` 读取 PostgreSQL 发布指针及不可变快照，不读取最新草稿。

Resolve 返回 sourceId/sourceDigest；Execute 必须带相同 expectedSourceId/expectedSourceDigest，服务端重新解析并比较，漂移返回 FAILED_PRECONDITION，不发起业务调用。PRT 与 ONLINE 严格隔离，即使旧共享 resolver 找到另一环境也拒绝执行。

ExecutionContext 的 userId 是有 presence 的 signed int64，允许完整范围，缺失拒绝；environment 仅 PRT/ONLINE；requestId 和 client 显式必填。模型业务 JSON 使用 bytes UTF-8 保留整数精度，不使用 protobuf Struct 的 double。COMMON 仅作者验证允许，运行态第一段只接受 PC/APP。

Python 引擎负责现有 use_skill/action_allowed/model_allowed 准入；Java 第一段仅接受受信内部引擎，不能替代上述产品准入。A2UI 使用已发布绑定和上下文验证后进入相同 `CapabilityExecutionPort`，没有新增 owner/admin 作为 B 端执行权限，也不新增写能力审批语义。

## 宿主配置

`ManualManagementConfiguration` 导入 `RuntimeRpcConfiguration`，收集 Ability 与 A2UI 的所有 BindableService。启动必填：

- `A2FLOW_RUNTIME_RPC_MODE=LOOPBACK` 或 `MTLS`；RPC 监听固定 `127.0.0.1`，不会开启公网监听。
- `A2FLOW_RUNTIME_RPC_PORT` 显式端口。
- `A2FLOW_CAPABILITY_GRPC_TARGETS_JSON`：按 targetKey、PRT/ONLINE 分组的对象，每个 endpoint 字段为 `host`、`port`、`loopbackPlaintext`、`trustCertFile`、`clientCertFile`、`clientKeyFile`。不存在目标环境时失败，不跨环境选择。空对象可启动但任何真实能力执行都会因无目标失败。
- MTLS 模式还需 `A2FLOW_RUNTIME_RPC_CERT_FILE`、`A2FLOW_RUNTIME_RPC_KEY_FILE`、`A2FLOW_RUNTIME_RPC_ENGINE_CA_FILE`。信任 CA 必须专用于内部引擎身份，不能使用面向公众客户端的 CA。

下游 `loopbackPlaintext=true` 仅允许显式 127.0.0.1 本机探针；其他目标必须配置三项 mTLS 证书路径。凭据来自宿主配置，不保存到草稿或模型上下文。管理 HTTP 的账号 Cookie 绝不进入能力 RPC。

## 验证边界

JDK17 Maven 自动从 proto 生成 Java/gRPC 类；可用 `-Dmanagement.build.directory=/absolute/isolated/build` 避免共享 target。执行 `PG_BIN=/path/to/postgres/bin bash backend/storage/db/tests/run-capability-rpc-probe.sh` 会新建独立 loopback PG 和两个真实 gRPC 服务，覆盖发布 DB 解析、双段二进制调用、signed64 精度、来源 pin、上下文覆盖拒绝、响应 schema、deadline、跨环境拒绝，退出停止 PG 并保留证据。

本地探针不是部署、真实业务服务接入或生产 mTLS 证书验收。业务方必须提供与注册 descriptor 一致的 gRPC 服务，并使用独立 context 作为身份来源。服务超时不等于业务未生效，NONE 策略不重试；需要业务幂等时应另行定义并批准语义。

官方 API 依据：[gRPC Java](https://grpc.io/docs/languages/java/basics/)、[Protobuf proto3](https://protobuf.dev/programming-guides/proto3/)。
