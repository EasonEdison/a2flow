# Regression Plan

- Status: `PLANNED`
- Executed cases: `0`
- Runtime evidence: none
- Environment: not provisioned

本文件只描述计划回归；表中结果均不是已验证事实。逻辑方法名将在主控裁决协议后映射到真实 HTTP/RPC 接口。

## Planned contract and runtime cases

| ID | Method | Params / setup | 预期成功 data 或错误 | 字段级断言 |
| --- | --- | --- | --- | --- |
| PC-01 | `CreateRevision` × 2 | 同一 AssetKey、同一 `expectedHeadRevision`、不同 payload/幂等键，两实例并发 | 一个 `RevisionRef`；一个 Problem Details | 成功 `revision=head+1` 且摘要非空；失败 `status=412`、`code=ASSET_HEAD_MISMATCH`；旧 revision 字节不变 |
| PC-02 | `CreateRelease` | 精确 RevisionRef、精确 dependencyReleases、固定幂等键 | `releaseId`、`assetRevision`、`dependencyReleases`、`contentDigest` | 返回引用与请求逐字段一致；重复同请求返回相同 `releaseId`；持久记录仅一条 |
| PC-03 | `CreateRelease` | 依赖使用 `latest` 或 Pointer | RFC 9457 校验错误 | `status=422`、`code=RELEASE_DEPENDENCY_NOT_PINNED`、`retryable=false`；无 Release/Pointer 变化 |
| PC-04 | `ActivateRelease` | 当前 pointerVersion=7；两个实例均期望 7，目标不同 | 一个 ActivationPointer；一个前置条件错误 | 胜者 `pointerVersion=8`；败者 `status=412`、`code=ACTIVATION_VERSION_MISMATCH`；最终只指向胜者 |
| PC-05 | `ActivateRelease` | 主体已认证但缺 `release.activate` | 授权错误 | `status` 符合隐藏策略、`retryable=false`；Pointer 不变；审计含主体引用/资源/拒绝结果且无 token/payload |
| PC-06 | `ResolveRelease` + Run resume | Run 先解析 A，之后 Pointer 切到 B 并重启 worker | 两次 Run binding | 原 Run `releaseId=A`、摘要/所见 pointerVersion 不变；新 Run 为 B；恢复不查询可变 head 替换 A |
| PC-07 | event consumer | 同一 `(source,id)` 重复两次，再交付 aggregateVersion 5 后 4 | 去重/顺序处理结果 | 副作用一次；投影不从 5 回滚到 4；缺口有可观测状态或重取记录 |
| PC-08 | `CreateRelease` × 2 | 两实例，同一幂等键；分别覆盖同请求与异请求 | 同请求同结果；异请求冲突 | 同请求 `releaseId` 一致；异请求 `status=409`、`code=IDEMPOTENCY_KEY_REUSED`；无重复 Release |

## Planned digest fixture

- 输入：一个公开、无敏感信息的 I-JSON manifest fixture。
- 步骤：至少用 Runtime 最终语言和前端/工具链语言分别执行 RFC 8785 规范化与 SHA-256。
- 期望：规范字节和 `sha256:<hex>` 完全一致；任何不一致阻止发布。

## Planned evidence capture

每次真实执行必须记录：代码/契约 SHA、PostgreSQL 版本、实例数、逻辑 method 与真实入口、脱敏 params、HTTP status、成功 `data` 字段、错误 `code/retryable/violations`、traceId、数据库字段级断言和重复副作用计数。没有这些证据不得把本文件改为 PASS。
