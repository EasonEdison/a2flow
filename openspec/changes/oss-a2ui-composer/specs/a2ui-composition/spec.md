# A2UI Composition Capability Specification

## Status

`PROPOSED / PHASE 1 ALIGNED`。权威基线 `SW-P1-20260907.2`。本文定义目标契约和已验证的合成样例边界，不代表 registry、Runtime、Host、部署或运行态证据。Runtime readiness 为 `NO READY`。

共享候选 `SW-CONTRACTS-P1-CANDIDATE.1` 已命名但尚未获 main-brain 批准；本文只声明消费需求，不复制其 schema 或把它当冻结接口。

## ADDED Requirements

### Requirement: M SHALL author Component Catalog and Application assets

系统 SHALL 将 Component Catalog 和 Application 作为 M 侧资产。Presentation SHALL 仅表示 Runtime 渲染产生的运行期输出，不得暴露第二套 Presentation Draft/Release 共享资产。

#### Scenario: Compile an Application instead of a Presentation asset

- GIVEN 一个引用精确 Component Catalog 的 ApplicationDraft
- WHEN Composer 校验并编译该草稿
- THEN 领域产物 kind 等于 APPLICATION
- AND 产物包含逻辑 Surface 模板与精确依赖锁
- AND 公共发布身份由 shared contracts 提供
- AND 不创建 Presentation 类型共享资产

### Requirement: Application SHALL declare interaction mode explicitly

每个 Application SHALL 显式声明 `DISPLAY_ONLY` 或 `INTERACTIVE`。Runtime MUST NOT 根据组件类型、模型输出、action 数量或渲染结果猜测是否暂停。

#### Scenario: Display-only Application does not pause

- GIVEN Application 的 interactionMode 为 DISPLAY_ONLY
- AND 其 actionPolicies 和交互 event 均为空
- WHEN `render_application` 成功渲染
- THEN Runtime 记录 RENDER_SUCCEEDED
- AND 当前执行不因该 Application 建立 interaction wait
- AND 后续节点仍由 Runtime 正常调度

#### Scenario: Interactive Application establishes scoped wait

- GIVEN Application 的 interactionMode 为 INTERACTIVE
- AND actionPolicy 绑定到合法 sourceComponentId
- WHEN `render_application` 成功渲染
- THEN Runtime 创建 node/card/form 范围的持久化 interaction
- AND 只有受信任 Action ingress 可以恢复
- AND 普通聊天输入不能恢复该 interaction
- AND 作者配置的确定性选择不经过 AI 重新判断

### Requirement: Action business success and interaction completion SHALL be separate

INTERACTIVE Application 的每个 ActionPolicy SHALL 引用 shared contracts 拥有的 `ResultCondition`，并 SHALL 显式声明 boolean `completeInteractionOnSuccess`。Action call success、业务 success 与 interaction completion MUST 分别记录。

#### Scenario: Successful business result completes interaction when configured

- GIVEN Action 调用成功
- AND ResultCondition 计算为 true
- AND completeInteractionOnSuccess 等于 true
- WHEN Runtime 记录 Action 结果
- THEN 记录 ACTION_CALL_SUCCEEDED
- AND 记录 ACTION_RESULT_SUCCEEDED
- AND 记录 INTERACTION_COMPLETED
- AND 节点后继可在 Runtime 规则允许时继续

#### Scenario: Successful business result keeps interaction open when configured

- GIVEN Action 调用成功
- AND ResultCondition 计算为 true
- AND completeInteractionOnSuccess 等于 false
- WHEN Runtime 记录 Action 结果
- THEN 记录 ACTION_RESULT_SUCCEEDED
- AND 不记录 INTERACTION_COMPLETED
- AND Runtime 等待后续显式 Action

#### Scenario: Business result does not satisfy success condition

- GIVEN Action 调用成功
- AND ResultCondition 计算为 false
- WHEN Runtime 记录结果
- THEN 记录 ACTION_RESULT_NOT_SUCCESS
- AND 不完成 interaction
- AND 只允许按 A2UI retry policy 处理该节点

### Requirement: Version admission SHALL precede new work

Runtime SHALL 在 execution、continue 和 Action ingress 做新工作前，通过 shared resolver 比较记录版本与当前有效版本。版本失配 MUST 返回 `RESET_REQUIRED`；系统 MUST NOT 继续冻结旧资产、静默迁移、自动重启或重放业务调用。

#### Scenario: Reject an Action on stale Application version

- GIVEN 历史交互记录的 Application 版本与当前有效版本不一致
- WHEN 用户提交 Action
- THEN Runtime 在调用业务 API 前返回 RESET_REQUIRED
- AND version guard mismatch 记录 recorded/effective version
- AND 业务 API 未被调用
- AND 历史卡进入只读
- AND 只有显式 reset 可以创建全新 run

### Requirement: Trusted identity and environment SHALL remain outside Application

Application、模型 Tool 参数和客户端 action payload MUST NOT 提供可信 `userId`、PRT/ONLINE 环境或 gray target。服务端 SHALL 从 shared trusted context 解析身份、环境和有效版本。PRT 只读 PRT 当前版本；ONLINE 只读 ONLINE stable/gray，不读 PRT。

#### Scenario: Reject embedded trusted context

- GIVEN 一个 Application fixture 含 userId、environment、grayTarget、credential 或 secret 字段
- WHEN Composer 校验
- THEN 校验失败
- AND 失败指向禁止字段
- AND 不产生可发布 payload

### Requirement: Action dedupe SHALL not claim business exactly-once

平台 `controlRequestId` SHALL 只去重控制请求。Application SHALL 声明业务幂等归属为被调 API 后端，不得把平台 control dedupe 表述为业务调用 exactly-once、补偿或对账能力。

#### Scenario: Preserve an uncertain external outcome

- GIVEN Runtime 已发出业务 Action 调用
- AND 网络失败导致结果未知
- WHEN 平台记录该 outcome
- THEN 不把重复 control response 当作业务成功
- AND 不自动重放业务 Action
- AND 不由 Workflow 执行补偿或跨 run 去重
- AND 后续策略服从被调 API 的业务幂等契约

### Requirement: A2UI node retry SHALL use a closed allowlist

首期节点 retry reason SHALL 严格限定为 `RENDER_FAILED`、`ACTION_CALL_FAILED`、`ACTION_RESULT_NOT_SUCCESS`。系统 MUST NOT 用该机制重试 Skill 模型调用、脚本、非 A2UI Tool 或其他通用失败。

#### Scenario: Accept all three A2UI retry outcomes

- GIVEN 一个 INTERACTIVE Application
- WHEN Composer 校验 retry policy
- THEN allowedReasons 精确包含三种 A2UI outcome
- AND 不包含重复或其他 reason

#### Scenario: Reject a generic Skill retry reason

- GIVEN retry policy 含 MODEL_FAILED
- WHEN Composer 校验
- THEN 校验失败
- AND 不产生 Application Release

### Requirement: Finalizer SHALL preserve facts and interaction boundaries

Finalizer MUST NOT 覆盖 Action 业务事实、将失败转成功、调用业务 Action、触发 retry 或绕过仍未完成的必需 interaction。

#### Scenario: Do not finalize through pending interaction

- GIVEN INTERACTIVE Application 已渲染
- AND 必需 interaction 尚未完成
- WHEN Runtime 进入 finalization boundary
- THEN Finalizer 不完成该 interaction
- AND 不产生虚假的 node/Skill/Workflow success
- AND 已保存的业务事实保持不变

### Requirement: Application rendering SHALL enter through render_application

Runtime SHALL 只通过授权 Tool `render_application` 消费 Application。Composer 产物保持 transport-neutral；Runtime 拥有 Surface、stream/cursor、等待/恢复和 Action dispatch；Host 拥有本地 React 映射与安全渲染。

#### Scenario: Fail closed on unsupported Host capability

- GIVEN Application 锁定某 protocol profile 与 Catalog digest
- AND Host 不支持该组合
- WHEN Runtime 调用 render_application
- THEN 返回 PROTOCOL_UNSUPPORTED 或 CATALOG_UNSUPPORTED
- AND 不创建可交互 Surface
- AND 不选择 latest/default Catalog
- AND 不下载执行代码
- AND 不产生业务 Action 副作用

### Requirement: Draft mutation and publication SHALL be PostgreSQL-correct

ComponentCatalogDraft 与 ApplicationDraft 更新 SHALL 提交 expectedRevision，并在 PostgreSQL 事务中 compare-and-swap。发布 SHALL 重新校验精确 revision、锁定依赖并原子创建不可变领域 payload；不得使用 MySQL、SQLite、内存 fallback、floating 或 latest 依赖。

#### Scenario: Reject a stale Application draft update

- GIVEN ApplicationDraft 当前 revision 为 7
- WHEN 调用方提交 expectedRevision=6
- THEN 返回 DRAFT_REVISION_CONFLICT
- AND currentRevision 等于 7
- AND 草稿内容与 revision 不变

#### Scenario: Publish immutable exact dependencies

- GIVEN ApplicationDraft 的 Catalog、ability output schema 与 Action contract 都是已授权精确 ReleaseRef/digest
- WHEN 使用公共 publication contract 发布
- THEN 返回不可变 Application ReleaseRef 与 artifactDigest
- AND dependencyLocks 完整
- AND 后续修改草稿不改变历史 Release
- AND 不存在 latest/default/draft fallback

## Cross-domain contract requirements

### platform-contracts input

本域需要 approved revision 提供 server-only trustedContext、effective version resolution、Asset/Release、ResultCondition、control request、outcome 与 publication envelope。候选 `SW-CONTRACTS-P1-CANDIDATE.1` 仅是审查输入。

### Runtime output expectation

Runtime 实现 `render_application`、版本准入、Surface、持久化 interaction、Action dispatch、A2UI-only retry、stop/restart 与 Finalizer 边界，并保持业务无关。

### digital employee output expectation

`packages/a2ui-host/` 提供 supported Catalog/profile、本地 React 映射、安全渲染、可访问性和可信 Action 回传；Host 无资产发布权。

## Acceptance gates

1. main-brain 批准 shared contract 与 A2UI protocol profile。
2. main-brain 下发命名 approved revision 和 registry IMPLEMENT。
3. registry Validator/PostgreSQL/publication 实现与测试完成。
4. Runtime 与 Host 联合证据覆盖 display、interactive、Action、version reset、retry 与 Finalizer。
5. readiness.md 的必要门禁全部 READY。
