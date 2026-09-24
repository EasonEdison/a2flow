# A2Flow 通用能力执行内核（Python）

本目录提供已发布 Protobuf gRPC 能力的纯 Python 执行内核。它只负责可信上下文门禁、模型参数校验、确定性请求绑定和统一结果；目标解析、Protobuf 描述校验及实际 gRPC 调用由 `transport.py` 负责。

## 接口

```python
transport: CapabilityTransport
executor = CapabilityExecutor(transport)

preview = executor.prepare(plan, arguments, trusted_context)  # 不发 RPC
result = executor.execute(plan, arguments, trusted_context)   # PC/APP 运行态
```

- `PublishedPlan` 是发布态不可变计划。仅支持 `source_type=GRPC`、`binding_type=GRPC`、`idempotency=NONE`、`response_policy=ORIGINAL`。
- `TrustedContext` 只接受宿主提供的 signed int64 `user_id`、`PRT/ONLINE` 环境、`request_id` 和 `client`。`execute` 仅放行与计划一致的 `PC/APP`；`COMMON` 只可用于作者态 `prepare` 预览。
- `CapabilityTransport.execute(plan, business, context) -> JsonValue` 是传输边界。传输层通过 `CapabilityTransportError` 返回稳定错误码，错误说明不得携带请求正文或凭据。

## 绑定和结果语义

模型只能提交计划声明的参数。内核递归校验 `string/number/integer/boolean/object/array`、对象必填字段和允许值；未声明字段以及 `url/uri/cookie/authorization/headers/header/host/token` 等目标或凭据字段直接拒绝。整数按 JSON Schema 语义无损归一，数组作为完整参数绑定，不支持数组下标路径。

映射顺序固定为：

1. 模型参数 `RequestMapping`；
2. 可信 `userId/client/env` 的 `ContextMapping`（`userId` 映射为规范十进制字符串）；
3. 发布态 `ConstantMapping`。

任意重复写入、点路径与标量冲突、可信枚举值映射缺失都会在出网前失败。模型参数不能覆盖独立 Protobuf `ExecutionContext`。

`ORIGINAL` 策略原样返回 transport 已通过技术 schema 校验的 JSON 值。内核不会看到 `code=500`、`success=false` 就自行改变业务语义，也不会筛选 `keyOutputFields`。传输成功与业务接口自身是否成功必须由上层依据该能力的公开契约判断。

## 当前边界

执行内核、权威发布读取/编译、入站 RPC 和 Host 已实现，配置和联调说明见 [中文运行手册](README.zh-CN.md)。不代表线上运行链路已经切换到 Python。以下内容仍未完成或不支持：

- 真实 M 页面场景资产发布、现有引擎流量切换与生产证书组装；
- 非 unary Protobuf、HTTP 回退、动态目标、数组下标映射、非 `ORIGINAL` 响应改写和非 `NONE` 幂等策略。

这些未支持项一律 fail closed，不自动回退到 HTTP 或其他环境/目标。

## 验证

使用仓库隔离环境：

```bash
cd services/capability-execution
/home/admin/OpenSource/.venvs/content-mvp/bin/ruff check src tests
MYPYPATH=src /home/admin/OpenSource/.venvs/content-mvp/bin/mypy -p a2flow_capability --explicit-package-bases
MYPYPATH=src /home/admin/OpenSource/.venvs/content-mvp/bin/mypy tests --explicit-package-bases
/home/admin/OpenSource/.venvs/content-mvp/bin/pytest -q
```

真实隔离 PostgreSQL 联调由 `deploy/capability_service/verify_published_content.py` 执行；需显式开启测试写入，不能使用线上数据库。
