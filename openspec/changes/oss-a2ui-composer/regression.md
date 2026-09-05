# A2UI 组件编排平台回归计划

## 当前结论

- 状态：PLANNED
- 已执行测试：0
- 构建证据：无
- 集成证据：无
- 部署证据：无
- 运行态证据：无
- Runtime readiness：NO READY

下面的方法、参数与响应字段均为 PROPOSED API 契约。只有实现完成、实际执行并记录时间、环境、命令和原始结果后，场景状态才可从 PLANNED 改为 PASS 或 FAIL。

## 公共断言

候选成功 envelope：

- requestId：非空且可关联审计日志。
- data：唯一业务结果对象；调用方不从 message 文案解析状态。

候选失败 envelope：

- requestId：非空。
- error.code：稳定机器码。
- error.message：人类可读但不作为程序契约。
- error.details：包含 jsonPointer、currentRevision 或 dependencyRef 等结构化证据。

## 计划场景

### P1 安全 Catalog 校验

- 状态：PLANNED
- Method：POST /api/a2ui/catalog-drafts/{draftId}:validate
- Params：draftRevision、明确 protocolProfile；已有合法 Catalog 文档。
- 期望 data：valid、reportDigest、errors、warnings、dependencyLocks、validatorRevision。
- 字段断言：valid=true；errors=[]；reportDigest 非空；protocolProfile 与草稿一致；重复请求 reportDigest 相同。
- 价值：证明 Catalog 校验确定且不依赖网络或进程状态。

### P2 非法组件图拒绝

- 状态：PLANNED
- Method：POST /api/a2ui/presentation-drafts/{draftId}:validate
- Params：draftRevision；Surface 含悬空 child 与不可达节点。
- 期望 data：valid、reportDigest、errors、warnings。
- 字段断言：valid=false；errors 同时含 DANGLING_COMPONENT_REFERENCE 与 UNREACHABLE_COMPONENT；每项有 jsonPointer。
- 后续断言：相同 revision 调 publish 返回 VALIDATION_FAILED，不产生 releaseRef。
- 价值：防止部分树进入 Runtime。

### P3 capability 输出绑定类型不兼容

- 状态：PLANNED
- Method：POST /api/a2ui/presentation-drafts/{draftId}:validate
- Params：draftRevision；Text 属性 binding 指向对象类型的精确 capability output schema Release。
- 期望 data：valid、errors、dependencyLocks。
- 字段断言：valid=false；error.code=BINDING_TYPE_MISMATCH；error.dependencyRef 精确匹配输入 Release；不创建运行记录。
- 价值：证明 capability 引用只用于定义期校验，不隐式执行能力。

### P4 草稿乐观并发

- 状态：PLANNED
- Method：PUT /api/a2ui/presentation-drafts/{draftId}
- Params：expectedRevision=6；数据库当前 revision=7；提交任意合法 mutable fields。
- 期望 error：DRAFT_REVISION_CONFLICT。
- 字段断言：error.details.currentRevision=7；数据库 revision 和内容未变化；两个 API 实例结果一致。
- 价值：证明多实例下不会丢失更新。

### P5 精确依赖不可变发布

- 状态：PLANNED
- Method：POST /api/a2ui/presentation-drafts/{draftId}:publish
- Params：draftRevision=4、完整 dependencyLocks；Header Idempotency-Key 为新值。
- 期望 data：releaseRef、artifactDigest、validationReportDigest、dependencyLocks。
- 字段断言：releaseRef 为精确不可变引用；artifactDigest 等于规范化 payload 重算值；依赖锁包含 Catalog/capability/action；不存在 latest/default 引用。
- 后续断言：更新 draft 到 revision=5 后，revision=4 的 Release 内容和 digest 不变。
- 价值：证明发布即冻结。

### P6 并发与重复发布收敛

- 状态：PLANNED
- Method：两个实例并发调用 POST /api/a2ui/presentation-drafts/{draftId}:publish
- Params：相同 draftRevision、publicationProfile、Idempotency-Key 与请求指纹。
- 期望 data：两个响应均含 releaseRef、artifactDigest。
- 字段断言：两个 releaseId 和 artifactDigest 完全相同；数据库只有一个有效 Release 和完整 payload。
- 反例断言：同一 Idempotency-Key 配不同请求指纹返回 IDEMPOTENCY_KEY_REUSED。
- 价值：证明网络重试和多实例竞争不会重复发布。

### P7 Runtime 精确解析与有序恢复

- 状态：PLANNED，归属 Runtime 联合契约测试。
- Method：Runtime 提议的 startPresentation/replayPresentation，最终名称待对齐。
- Params：exact releaseRef、artifactDigest、runId、attemptId、rendererCapabilities、dataModel、resumeCursor。
- 期望 data：surfaceId、protocolProfile、catalogId、nextCursor、orderedEnvelopes。
- 字段断言：先 createSurface 后依赖 Surface 的更新；cursor 单调；断线后从持久化 cursor 重放；无数字员工业务字段。
- 价值：证明 Composer Artifact 可由通用 Runtime 执行，但本域不承担运行状态。

### P8 Renderer 不支持时失败关闭

- 状态：PLANNED，归属 Runtime 与数字员工联合契约测试。
- Method：Runtime 提议的 negotiatePresentation/startPresentation。
- Params：Presentation 锁定 catalogA@digest1；Renderer 仅支持 catalogB@digest2。
- 期望 error：CATALOG_UNSUPPORTED。
- 字段断言：不创建 Surface；不尝试 catalogB/latest/网络下载；不产生 action 或 capability 副作用；错误可用 runId/requestId 关联。
- 价值：证明三方不会用隐式兼容掩盖契约不一致。

## 执行记录模板

每个场景执行后必须补充：

- 执行时间与提交 SHA
- 环境与 PostgreSQL 版本
- 实际命令或测试类
- 请求 method/params 和已脱敏输入摘要
- 成功 data 字段或失败 error 字段原始断言
- 多实例拓扑与并发方式
- PASS/FAIL/PARTIAL
- 未覆盖风险

当前不得填写虚构结果。
