# A2UI 组件编排平台回归记录

## 当前结论

- 基线：`SW-P1-20260907.2`
- 内容提交/首次服务器 main 集成：`c624c4f695cfe621464cc8b44d1823e85c1fab9f`
- main-brain review hardening/服务器 main 集成：`3eac2f9de3a7b306b62a5175dae374d550223959`
- 合成夹具静态校验：`PASS`
- Registry build/API/PostgreSQL：`NO READY`
- Shared contract：`SW-CONTRACTS-P1-CANDIDATE.1` 固定快照 54/54 GREEN，但仍未批准
- Runtime/Host 联合验证：`NO READY`
- Deployment/E2E：`NO READY`
- 总体 Runtime readiness：`NO READY`

静态夹具只证明本域候选语义能被确定性拒绝/接受，不证明 shared schema 已冻结，不证明 `render_application`、Action dispatch、Host 或数据库实现存在。

## 已执行证据

### R1 两份合成 Application 正例

- 状态：`PASS`
- 时间：`2026-09-07T02:01:16+08:00`
- 环境：服务器 worker worktree；Node `v20.20.2`；无依赖安装、无网络 schema 访问
- Command：`node --test packages/a2ui-contract-fixtures/test/validate-fixtures.test.mjs`
- Result：`tests 20, pass 20, fail 0`
- 字段级断言：
  - 两份 fixture 都是 synthetic、`PROVISIONAL`、`APPLICATION`，baseline 为 `SW-P1-20260907.2`。
  - protocolProfileRef 保持 `PENDING_CROSS_DOMAIN_REVIEW`。
  - render Tool 为 `render_application`。
  - DISPLAY_ONLY 不暂停、无 Action、retry 仅 `RENDER_FAILED`。
  - INTERACTIVE 暂停且绑定 node/card/form，普通聊天不能恢复，确定性选择不经 AI 重选。
  - Action 使用精确 abilityReleaseRef + successPolicyRef 选择 shared ResultInterpretationPolicy，并显式声明 `completeInteractionOnSuccess`；内联 DSL、inline policy 字段与旧 businessSuccessConditionRef 都会被拒绝。
  - 平台仅 `controlRequest` 去重，业务幂等 owner 为 `CALLED_API_BACKEND`。
  - execution、continue 与 Action ingress 都要求先做版本比较；失配返回 `RESET_REQUIRED`。
  - Finalizer 不改写业务事实、不绕过必需交互。
  - 禁止嵌入 userId/environment/grayTarget/secret/credential/script/html。
  - Action policy 的 actionName/sourceComponentId 非空且唯一，并与组件 event 双向一一覆盖。
  - abilityReleaseRef 拒绝 latest/default/draft，retry reasons 拒绝重复项。

### R2 目录级校验

- 状态：`PASS`
- Command：`node packages/a2ui-contract-fixtures/validate-fixtures.mjs --directory packages/a2ui-contract-fixtures/fixtures`
- Result：`validated 2 synthetic Application fixtures`
- 断言：目录精确包含两份 `*.application.json`，每份分别通过结构、组件图和策略检查。

### R3 A2UI-only retry 负例 TDD

- 状态：`PASS`
- RED：删除 INTERACTIVE fixture 中 `ACTION_CALL_FAILED` 与 `ACTION_RESULT_NOT_SUCCESS` 后，旧校验器未抛异常，测试以 `Missing expected exception` 失败。
- GREEN：新增 exact-set 校验后，同一变异 fixture 被拒绝；随后加入 policy 引用/内联、信任/三入口版本/交互/Finalizer 等负例。
- 价值：证明 allowlist 不仅拒绝额外 reason，也拒绝缺少任一必需 A2UI outcome。

### R4 main-brain review 六类反例

- 状态：`PASS`
- RED：新增 policy 身份缺失、重复 policy、无 policy event、单数 credential、`@latest` release、重复 retry reason 六个内存变异后，原 validator 结果为 `tests 20, pass 14, fail 6`。
- GREEN：分别补充 trusted-key、retry Set 长度、非 floating release 与 Action/event 双向唯一覆盖后，最终结果为 `tests 20, pass 20, fail 0`。
- targeted 证据：credential、retry、latest 各 1/1 PASS；Action identity/duplicate/event coverage 为 3/3 PASS。
- 边界：只证明 fixture checker 失败关闭；不证明 shared ReleaseRef 存在性、Runtime 或业务凭据泄露。

## 待实现联合场景

### P1 DISPLAY_ONLY 渲染后继续

- 状态：`PLANNED / Runtime`
- Method：`render_application`
- Params：精确 Application ReleaseRef、run/node/attempt、trusted context ref、dataModel。
- 成功 data/outcome：RENDER_SUCCEEDED、surfaceId、`requiresPause=false`。
- 断言：不创建 interaction，不阻断后继，不把 render success 记为 Skill/Workflow success。

### P2 INTERACTIVE 渲染并等待

- 状态：`PLANNED / Runtime + Host`
- Method：`render_application`
- Params：INTERACTIVE Application 与支持的 Host capabilities。
- 成功 data/outcome：RENDER_SUCCEEDED、surfaceId、interactionId、`requiresPause=true`。
- 断言：持久化 node/card/form 绑定；普通聊天无法 resume；Host Action 可关联来源组件。

### P3 Action 业务成功并完成交互

- 状态：`PLANNED / Runtime`
- Method：受信任 `SUBMIT_INTERACTION` 候选控制命令。
- Params：runId/nodeId/interactionId/surfaceId/sourceComponentId、recordedAssetVersions、payload digest。
- 成功 data/outcome：ACTION_CALL_SUCCEEDED、ACTION_RESULT_SUCCEEDED、INTERACTION_COMPLETED。
- 断言：输出 schema 合法、success policy matched 且 `completeInteractionOnSuccess=true`；schema validity、policy matched、Action call success 与 interaction completion 分别存在。

### P4 Action 业务成功但保持交互

- 状态：`PLANNED / Runtime`
- Method/Params：同 P3，但 `completeInteractionOnSuccess=false`。
- 期望：有 ACTION_RESULT_SUCCEEDED，无 INTERACTION_COMPLETED，后继不启动。

### P5 Action 结果不满足成功条件

- 状态：`PLANNED / Runtime`
- 期望：ACTION_CALL_SUCCEEDED 与 ACTION_RESULT_NOT_SUCCESS 分开记录；交互保持；只可按对应 A2UI retry reason 有界重试。

### P6 版本失配阻断 Action

- 状态：`PLANNED / contracts + Runtime`
- Params：recordedAssetVersions 与 effective version 不同。
- 期望 error/data：`RESET_REQUIRED` 与非空 mismatches。
- 断言：比较发生在业务调用前；零业务调用；历史卡只读；无自动迁移/重启/重放。

### P7 Finalizer 不越权

- 状态：`PLANNED / Runtime`
- Params：未完成交互与已记录失败事实。
- 断言：Finalizer 不调 Action、不 retry、不完成交互、不将 node/Skill/Workflow 标为成功。

### P8 Host 不支持时失败关闭

- 状态：`PLANNED / Runtime + Host`
- Params：Application 锁定的 protocol/Catalog 与 Host capabilities 不匹配。
- 期望 error：PROTOCOL_UNSUPPORTED 或 CATALOG_UNSUPPORTED。
- 断言：不建可交互 Surface、不 fallback、不下载代码、不产生业务副作用。

### P9 PostgreSQL 多实例与不可变发布

- 状态：`PLANNED / registry`
- Method：Application Draft update/validate/publish 候选 API。
- 断言：expectedRevision 冲突、精确 dependencyLocks、原子 publication、控制请求幂等、多实例唯一约束；无 SQLite/MySQL/内存 fallback。

## 证据纪律

联合场景只有在记录以下信息后才能改为 PASS：

- 执行时间、worker/content SHA 与服务器 main integration SHA
- 工具与依赖版本
- 实际 method/params 或测试命令
- 成功 data 或失败 error 的字段级断言
- 多实例/数据库拓扑（适用时）
- 未覆盖风险

本文件不填写虚构的 API、数据库、部署或运行结果。
