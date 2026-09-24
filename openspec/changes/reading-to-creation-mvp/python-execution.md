# Python 业务能力执行迁移：第一批

2026-09-24。本批实现执行内核与下游 Protobuf 传输，不切换现有线上 Java 服务。

## 保留的行为

- 只有 M 端保留 Java；运行态目标为 Python。本批为该迁移的组成部分，不代表迁移结束。
- 业务参数来自已声明的模型参数，经类型校验与配置映射后形成下游请求；可信 userId/environment/requestId/client 单独注入。
- 服务端 targetKey + 精确环境选择 RPC 地址；无 HTTP、跨环境、默认地址或凭据降级。
- 只接受注册的 unary 方法及包含完整导入的 FileDescriptorSet；平台 ExecutionContext 的描述必须逐字段一致。
- 采用官方 Protobuf 动态消息与 ProtoJSON 转换，不下载代码或按模型指定地址调用反射服务。signed int64 不经过浮点 Struct。
- ORIGINAL 响应保留完整数据，业务 success/result 判断仍由既有配置及上层结果策略负责，不新增固定业务码含义。

## 当前验证

root 的真实 loopback gRPC 验证已覆盖：最大 signed int64 注入、保留上下文不可覆盖、未知字段拒绝、缺少精确环境目标拒绝、外部 schema 引用拒绝、返回 schema 不匹配拒绝、伪造平台 descriptor 和 streaming 方法拒绝。

已完成组合验证：`CapabilityExecutor` 将声明的 `projectTitle` 映射成 Protobuf `title`，通过 `GrpcTransport` 调用测试 ContentService 并返回真实响应。内核与传输联合 strict mypy、Ruff 通过；测试最终计数在 regression.md 记录。

主线程复核发现并修正一项映射边界：已写入的 `a=null` 不能在后续 `a.b` 映射时被静默替换为对象；与已有标量冲突一样拒绝执行。

实际下游使用测试 ContentService 实现，证明跨 gRPC 传输和映射边界，不等同于真实内容数据库或公开产品链路验收。内容服务自己的真实 PG 证据见 regression.md。

## 未交付

1. 从 M 已发布数据库重建执行计划、按 userId 灰度选择并比对 sourceId/digest；不能用直接传入 PublishedPlan 代替该授权入口。
2. Python CapabilityExecution 入站 host 与实际配置组装；现有引擎尚未改连新服务。
3. Python A2UI Load/Action/ResultAdapter 迁移。
4. M 场景资产录入发布、真实模型 Chat、三节点 Workflow、公网部署与浏览器验收。

## 官方实现依据

- [Protobuf Python API](https://protobuf.dev/reference/python/python-generated/)
- [官方动态消息工厂](https://github.com/protocolbuffers/protobuf/blob/main/python/google/protobuf/message_factory.py)
- [gRPC Python channel API](https://grpc.github.io/grpc/python/_modules/grpc.html)

使用项目锁定版本验证实际 API；不因在线文档版本变化而直接升级运行中依赖。
