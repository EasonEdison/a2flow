# 公共平台契约与发布语义提案

- Design status: `PROPOSED`
- Evidence label: `C`（已设计，未实现、未验证）
- Runtime readiness: `NO READY`
- Owner: `oss-platform-contracts`

## 为什么现在需要这项 change

四个 M 端平台注册、B 端通用 Runtime 与数字员工产品都要引用同一份资产，但当前尚未统一“资产是谁、某次修改是哪一版、发布后能否改变、哪个版本正在生效、谁有权切换、失败与事件如何表达”。如果六个领域各自定义，引用会漂移，运行恢复也无法证明使用的是同一发布快照。

本 change 只定义跨域最小公共语义，不替 Skill、Capability、A2UI、Workflow、Runtime 或数字员工领域拥有业务状态机。

## 范围

- 稳定资产身份、不可变 revision 与精确引用。
- 不可变 Release 和可并发保护的 Activation Pointer。
- 人类/服务主体的通用授权上下文与审计身份。
- HTTP 错误信封、事件信封、幂等、重试、去重和顺序边界。
- 六个领域必须回交给主控的接口需求。

## 明确不在范围内

- 领域审批流、校验流、上下线状态机或 Workflow 运行状态机。
- 具体 REST 路径、RPC 技术、消息中间件、语言 SDK 与协议版本最终冻结。
- 组织计费、复杂租户管理、数据库 DDL、代码、部署和运行态验证。

## 候选方案

### A. 身份、Revision、Release、Pointer 四层分离（推荐）

稳定 `AssetKey` 标识逻辑资产；每次编辑产生不可变递增 `Revision`；通过领域门禁后生成不可变 `Release`，冻结精确依赖与摘要；每个生效环境只维护一个可 CAS 更新的 `ActivationPointer`。Runtime 在一次 Run 开始时解析并钉住精确 Release。

优点是作者态、发布态与运行态证据清楚，支持多实例并发和恢复；代价是对象多一层，需要共同实现解析和审计。

### B. 仅使用语义版本作为身份

以 `name@semver` 同时表达修改和发布。阅读友好，但预发布、回滚、重发与并发写入容易混淆；不同资产类型也很难共享兼容性规则。

### C. 仅使用内容摘要

一切由 `sha256` 内容寻址。不可变性最强，但用户可读性、授权资源、审计和环境切换都需要额外索引，不能单独替代逻辑身份和生效指针。

## 推荐

采用 A，并把内容摘要作为 Release 的完整性锚点，而不是把摘要当作唯一业务身份。推荐默认值如下，均需主控审查后才进入实现：

- `assetId` 与 `releaseId` 使用 UUIDv7；名称/slug 只是可变展示或查询别名。
- revision 是单资产内从 1 开始的正整数，创建后不原地修改。
- JSON 发布载荷按 RFC 8785 规范化后计算 `sha256`；非 JSON 载荷按存储的规范字节计算。
- Pointer 必须带 `pointerVersion` 并通过 HTTP `If-Match` 或等价 CAS 更新；不提供静默覆盖。
- 错误采用 RFC 9457 Problem Details 扩展；领域代码保留机器可读稳定性。
- 事件采用 CloudEvents 1.0 信封，交付语义为至少一次，消费者按 `(source,id)` 去重。

## 预期影响

- 六个领域可以独立定义业务 payload，但必须用同一 Asset/Release/Pointer 引用和错误、事件外壳。
- Runtime 只消费精确 Release，不依赖 M 端可变草稿，也不把数字员工业务模型引入核心。
- PostgreSQL 成为唯一正确性存储；多实例之间不得依赖本机内存锁、缓存或进程内事件。

## 风险与缓解

- 过早冻结协议：本轮只标 `PROPOSED`，具体传输与语言由主控统一裁决。
- 摘要不一致：明确规范字节算法和算法前缀，并用跨语言固定样例验证。
- 重试造成重复发布：创建类命令要求幂等键，同键同请求返回原结果，同键异请求拒绝。
- Pointer 竞争丢失更新：强制 CAS；失败方重新读取后显式决定，不自动重放覆盖。

## 公开依据

- [RFC 9562 UUID](https://www.rfc-editor.org/rfc/rfc9562.html)
- [RFC 7519 JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html)
- [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html)
- [RFC 9110 HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9457 Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [CloudEvents Specification](https://github.com/cloudevents/spec/blob/ce@v1.0.2/cloudevents/spec.md)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)

## 交付解释

本提案进入 `main` 只表示设计源码已提交审查，不表示主控批准、实现完成、部署完成或 Runtime 可用。
