# 内部 RPC 契约

## Python 内容业务服务（阅读到创作）

新增 `proto/a2flow/content/v1/content.proto`，11 个明确方法覆盖项目、素材、产物、确认和导出。每个请求引用既有 `ExecutionContext`，不转发 Cookie；可信身份由经过服务认证的执行端注入。正文使用 `ArtifactBody` oneof 区分阅读简报、选题单和稿件，确认结果也有明确字段；ProtoJSON 是普通嵌套对象，不要求模型或 M 端用户填写 Base64 或 JSON 字符串。签名中的 kind 与实际 body 必须由业务服务交叉校验。

运行 `bash packages/rpc-contracts/scripts/generate-content.sh` 生成 Python 与 mypy 类型声明；用 `PYTHON_BIN` 指定隔离工具环境，PATH 须包含同环境的 protoc-gen-mypy 工具。可选 `DESCRIPTOR_OUTPUT=/absolute/path/content.pb` 输出带依赖的描述文件用于能力注册。共用身份 proto 目前仍在旧管理源码目录；引用该文件不表示内容服务依赖 Java 进程。

运行 `PYTHONPATH=packages/rpc-contracts/src python -m unittest discover -s packages/rpc-contracts/tests` 验证传输结构、身份精度和版本 presence；这不替代真实 RPC、身份校验或 PostgreSQL 联调。生成器使用本文件既有固定工具版本，禁止手改生成代码。

新目标是仅 M 端 Java、业务与运行态执行 Python。下文描述原有客户端兼容基线；旧 Java 发布选择/执行尚需独立迁移验收。首批内容服务不能被描述为整个 Chat 链路已经切换 Python。

Python 模块由 Java 管理候选的 `proto/a2flow/{capability,a2ui}/v1/*.proto` 通过公开 `grpcio-tools==1.75.1` 生成，不手改生成代码。RPC 是服务间协议，不是浏览器 API。

运行代码生成命令：`python -m grpc_tools.protoc -I "$PROTO_ROOT" --python_out=src --grpc_python_out=src a2flow/capability/v1/capability.proto a2flow/a2ui/v1/a2ui.proto`。

类型文件由公开 `mypy-protobuf==3.7.0` 生成：相同 proto 输入加 `--mypy_out=src --mypy_grpc_out=src`，确保 `protoc-gen-mypy` 和 `protoc-gen-mypy_grpc` 在 PATH。不要使用 protoc 原生 `--pyi_out` 覆盖更精确的类型文件。`typing` 可选依赖记录本轮实际验证版本；没有全局跳过 generated 检查。

业务动态 JSON 使用 UTF-8 bytes，避免 `Struct` 将 signed64 转成 double。身份使用显式存在性检查的 int64，环境必须是 PRT 或 ONLINE。生产通道必须使用客户端证书及服务端 CA；仅显式本地测试模式允许 loopback 明文。

## Python 客户端

入口 `agent_workflow_runtime.rpc_client.RpcClient.from_environment(mapping)`，必要配置：

- `A2FLOW_ENGINE_RPC_TARGET=host:port`
- `A2FLOW_ENGINE_RPC_MODE=MTLS`：同时要求 `A2FLOW_ENGINE_RPC_CA_FILE`、`A2FLOW_ENGINE_RPC_CERT_FILE`、`A2FLOW_ENGINE_RPC_KEY_FILE`。客户端验证服务端 CA 与名称，服务端必须验证客户端 CA。
- 仅本地独立验证可明确配置 `MODE=LOOPBACK`，目标只能是字面 loopback IP。无证书缺失自动降级。
- `A2FLOW_ENGINE_RPC_TIMEOUT_SECONDS` 默认 10；`A2FLOW_ENGINE_RPC_CLIENT` 默认 PC，仅 PC/APP，COMMON 是配置层公共计划而非实际客户端身份。

每次调用显式传入既有 `TrustedContext(user_id, environment)` 和 requestId；它们必须来自已鉴权服务上下文，不合并浏览器或模型参数。

```python
description = rpc.describe(owner, app_code, request_id)
result = rpc.activate(owner, app_code, params, description.release, request_id)
ability = rpc.resolve(owner, asset_key, request_id)
output = rpc.execute(owner, asset_key, arguments,
                     ability.source_id, ability.source_digest, request_id)
```

实际入口必须先执行 Skill 依赖闭包版本校验，并将 runtime PG 中已读取的发布身份传给 `activate/execute`；不要用临时 Describe 新身份绕开旧 Skill/card 的 reset 判断。`act(owner, trusted_card, action_message, request_id, correlation_id=card_id)` 只接受服务端持久化卡片，包含 session、revision 和恢复快照。

返回值为 frozen dataclass；动态 JSON 是只读 Mapping/tuple。数据库或页面投影使用 `thaw(value)` 得到独立 dict/list，整数不经过浮点转换。卡片 session 仅保存在私有绑定元数据，不得向浏览器输出。

`RpcFailure` 继承 `ActionRejected`。发布不一致稳定映射 `RESET_REQUIRED`；超时返回 `RPC_TIMEOUT_OUTCOME_UNKNOWN`，明确不代表业务没执行。禁用 gRPC 自动重试，不打印证书、私钥、业务响应或完整参数。Application 本身的 source 身份在业务调用前核对；依赖闭包入口检查与后续单个能力调用之间仍存在版本变化窗口，当前不声称跨资产强快照。

## 可复跑验证

设置 `PYTHONPATH` 包含本包 `src`、`packages/contracts/src` 和 `services/agent-workflow-runtime/src`，在已安装项目 Runtime 依赖及本包依赖的解释器运行：

`python services/agent-workflow-runtime/tests/test_rpc_client.py`

该测试启动临时 loopback gRPC 测试服务，验证五种调用、signed64 精度、返回值深冻结、source/environment 核对、reset、超时只调用一次、配置失败关闭。它不是生产 mTLS、真实业务 RPC、PostgreSQL 发布或浏览器验收的替代品。
