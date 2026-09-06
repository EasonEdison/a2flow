# A2UI 组件编排平台实施任务

## 状态说明

Phase 1 已授权 ALIGN/PROVE。勾选只表示本任务真实完成的设计或静态夹具工作；共享契约、registry、Runtime、部署和运行态仍按独立门禁判断。当前权威基线为 `SW-P1-20260907.2`。

## 1. Phase 1 ALIGN

- [x] 1.1 同步并读取 `SW-P1-20260907.2`，记录 PY-01 仅授权 Runtime 必要时协调修改系统 Python。
- [x] 1.2 将当前设计从 Presentation 资产改为 Component Catalog/Application。
- [x] 1.3 明确 DISPLAY_ONLY/INTERACTIVE、Action 成功/完成分离、Finalizer、版本 reset 和 A2UI-only retry。
- [x] 1.4 向 contracts owner 提交 trusted context、版本准入、结果解释策略、控制请求、outcome 和 retry 需求。
- [x] 1.5 收到候选 `SW-CONTRACTS-P1-CANDIDATE.1`；记录为未批准依赖，不据此冻结 registry 实现。
- [x] 1.6 向 Runtime/Host 暴露 `render_application`、交互绑定、Action ingress 与失败关闭需求。
- [x] 1.7 读取 ENG-01：future A2UI registry 后端使用 Python 可导入模块，但不据此启动服务或编辑 root dependency files。
- [x] 1.8 校验并读取 `SW-P1-SUBSET-01`：只确认共享 ResultInterpretationPolicy 定义子集获准实现，A2UI Action/profile/Registry/Host 未放行。

## 2. Phase 1 独立契约夹具

- [x] 2.1 新增合成 DISPLAY_ONLY 结果卡 Application。
- [x] 2.2 新增合成 INTERACTIVE 选择卡 Application。
- [x] 2.3 实现无依赖校验器，覆盖组件图、交互/完成、版本、Finalizer、信任边界和 retry allowlist。
- [x] 2.4 用 Node 内置 test runner 记录 RED/GREEN，并执行目录级校验。
- [x] 2.5 标记夹具为 `PROVISIONAL`/synthetic，不包含真实业务数据，不冻结 A2UI 版本。
- [x] 2.6 按 main-brain review 增加 Action/event 双向唯一覆盖、单数 credential、非 floating release 与重复 retry reason 负例。

## 3. 共享契约审查门禁

- [ ] 3.1 main-brain 批准或修订 `SW-CONTRACTS-P1-CANDIDATE.1`。
- [ ] 3.2 冻结公共 AssetRef/ReleaseRef、digest、授权、审计和 publication envelope。
- [ ] 3.3 冻结 trustedContext、effective version resolver 与 RESET_REQUIRED envelope。
- [ ] 3.4 冻结 ResultInterpretationPolicy 解释规则及 Action/interaction/node/run outcome envelope。
- [ ] 3.5 冻结 Runtime/Host transport、cursor、Catalog negotiation 和 Action ingress 字段。
- [ ] 3.6 main-brain 命名 approved contract revision 并明确下发 registry IMPLEMENT。
- [ ] 3.7 main-brain 审查 `services/a2ui-registry/` 的 exact Python package layout 与必要依赖；root manifests 仍由 coordinator 独占。

## 4. PostgreSQL 草稿与发布模型（待放行）

- [ ] 4.1 实现 ComponentCatalogDraft、ApplicationDraft、revision 与审计持久化。
- [ ] 4.2 实现 expectedRevision compare-and-swap 与 DRAFT_REVISION_CONFLICT。
- [ ] 4.3 实现 validation report、publication request 与不可变领域 payload。
- [ ] 4.4 增加多实例唯一约束、原子事务与迁移验证。
- [ ] 4.5 确认无 MySQL、SQLite 或内存 fallback。

## 5. Catalog/Application Registry API（待放行）

- [ ] 5.1 实现 Catalog Draft create/update/read/validate/publish。
- [ ] 5.2 实现 Application Draft create/update/read/validate/publish。
- [ ] 5.3 接入批准的 shared contract envelope，不复制可信上下文或版本 resolver。
- [ ] 5.4 实现精确 Release 读取，不提供 latest/default/draft fallback。
- [ ] 5.5 实现授权和脱敏审计日志。

## 6. Validator 与编译（待放行）

- [ ] 6.1 固定 main-brain 批准的 A2UI schema bundle 与 validatorRevision。
- [ ] 6.2 实现离线 schema/Catalog 语义校验。
- [ ] 6.3 实现 root、唯一 ID、引用、环、可达性和资源上限校验。
- [ ] 6.4 实现 JSON Pointer、数据类型、Action contract 与 successPolicyRef 引用校验。
- [ ] 6.5 实现确定性编译、规范化和领域 payload digest。
- [ ] 6.6 拒绝脚本、可信上下文字段、未批准 ref、危险 URL 和超限资产。

## 7. 联合验证（待跨域实现）

- [ ] 7.1 `render_application` 对 DISPLAY_ONLY 不暂停，对 INTERACTIVE 建立持久化等待。
- [ ] 7.2 Action ingress 在调用前执行版本准入，失配返回 RESET_REQUIRED 且不产生业务调用。
- [ ] 7.3 Action 调用成功、业务成功、交互完成、节点/Skill/Workflow 完成分别有字段级证据。
- [ ] 7.4 retry 只覆盖三种 A2UI outcome，stop/restart/Finalizer 不扩展边界。
- [ ] 7.5 Host 对不支持的协议/Catalog/组件失败关闭，无下载或 fallback。
- [ ] 7.6 PostgreSQL 多实例、发布事务与控制请求去重通过集成测试。

## 8. 准出

- [x] 8.1 当前改动范围限于本任务专属 change 与 `packages/a2ui-contract-fixtures/`。
- [ ] 8.2 main-brain 对实际 diff、候选依赖和证据完成审查。
- [x] 8.3 内容提交 `c624c4f…`、canonical 修正 `7b1257a…` 与 review hardening `3eac2f9de3a7b306b62a5175dae374d550223959` 均已 push，并通过独占 integration worktree 合入服务器 `origin/main`。
- [ ] 8.4 所有必要门禁达到 READY 后才能宣称实现或运行可用。
