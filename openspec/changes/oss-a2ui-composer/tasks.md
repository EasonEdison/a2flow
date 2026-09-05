# A2UI 组件编排平台实施任务

## 状态说明

本文只记录未来实现工作。当前设计为 PROPOSED，尚未获准实施；因此所有任务均未勾选。设计文档已写入不等于以下实现任务完成。

## 1. 跨域契约冻结

- [ ] 1.1 与 oss-platform-contracts 对齐 AssetRef、ReleaseRef、digest、授权、审计、Idempotency-Key 和请求指纹。
- [ ] 1.2 与 oss-capability-registry 对齐 capability output schema 与 action contract 的精确 Release 读取。
- [ ] 1.3 与 oss-agent-workflow-runtime 对齐 PublishedPresentationResolver、协议 profile、cursor、replay 和 action correlation。
- [ ] 1.4 与 oss-digital-employee 对齐 supportedCatalogIds、React Renderer mapping、安全渲染、可访问性和 action 回传。
- [ ] 1.5 由 main-brain 记录 A2UI 版本、传输绑定与重新评估触发器 ADR。

## 2. PostgreSQL 草稿模型

- [ ] 2.1 实现 CatalogDraft、PresentationDraft、revision 与审计持久化。
- [ ] 2.2 实现 expectedRevision compare-and-swap 和 DRAFT_REVISION_CONFLICT。
- [ ] 2.3 实现 validation_report、publication_request 与不可变领域 payload 表。
- [ ] 2.4 增加多实例需要的唯一约束、事务回滚与迁移验证。
- [ ] 2.5 确认无 MySQL、SQLite 或内存持久化 fallback。

## 3. Catalog 与 Presentation API

- [ ] 3.1 实现 Catalog Draft create/update/read/validate/publish API。
- [ ] 3.2 实现 Presentation Draft create/update/read/validate/publish API。
- [ ] 3.3 实现统一成功 data 与类型化 error envelope。
- [ ] 3.4 实现精确 Release 读取，不提供 latest/default/draft fallback。
- [ ] 3.5 实现授权校验与不含正文/敏感上下文的审计日志。

## 4. 校验与编译

- [ ] 4.1 固定批准的 A2UI schema bundle、ProtocolProfile 与 validatorRevision。
- [ ] 4.2 实现离线 JSON Schema 2020-12 与 Catalog 语义校验。
- [ ] 4.3 实现 root、唯一 ID、引用、环、可达性和资源上限校验。
- [ ] 4.4 实现 JSON Pointer、数据类型、capability schema 与 action contract 兼容校验。
- [ ] 4.5 实现确定性编译、JSON 规范化和领域 payload digest。
- [ ] 4.6 拒绝脚本、未批准 schema ref、危险 URL scheme 和超限资产。

## 5. 不可变发布

- [ ] 5.1 接入公共 Release Port，不复制公共发布语义。
- [ ] 5.2 实现发布前重新校验与完整 dependencyLocks。
- [ ] 5.3 实现 Idempotency-Key/requestFingerprint 持久化和冲突检测。
- [ ] 5.4 实现并发发布收敛、瞬时失败同 key 重试与部分写入回滚。
- [ ] 5.5 验证发布后修改草稿不会改变历史 Release。

## 6. Runtime 与 Renderer 契约适配

- [ ] 6.1 提供 Runtime 可解析的 transport-neutral Presentation Artifact。
- [ ] 6.2 完成与 Runtime 的 exact release/digest/protocol 错误契约测试。
- [ ] 6.3 完成与 Renderer 的 Catalog capability negotiation 契约测试。
- [ ] 6.4 验证 unsupported Catalog 不 fallback、不下载、不产生副作用。
- [ ] 6.5 验证 action 元数据可被 Runtime 关联并幂等去重。

## 7. 验证与准出

- [ ] 7.1 完成 Validator 规则表驱动单测与属性测试。
- [ ] 7.2 完成 PostgreSQL 多实例并发、唯一约束和事务恢复集成测试。
- [ ] 7.3 完成八个 change-local 验收场景并把证据写入 regression.md。
- [ ] 7.4 完成 clean-room、依赖许可证与敏感信息检查。
- [ ] 7.5 所有必需门禁为 READY 后，由 main-brain 决定是否批准实现和归档。
