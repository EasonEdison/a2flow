# Phase 1 任务

> Baseline: SW-P1-20260907.2 + ENG-01。勾选只代表本任务源码/文档证据，不代表接口批准或 Runtime READY。

## 1. ALIGN

- [x] 1.1 worker 已在提交前再次 fetch/merge `origin/main` 到 `0980f0ae304a340f24d7421ab4a51818af612b32`。
- [x] 1.2 识别并移除 preview/stable、workspaceId/issuer、frozen continuation、业务幂等和协议预冻结冲突。
- [x] 1.3 向 main-brain 回传基线、独占范围、首个切片和真实依赖。

## 2. CONTRACT candidate

- [x] 2.1 先创建 Schema 正反例和聚焦校验入口，并观察缺失 Schema 的 RED。
- [x] 2.2 实现 TrustedContext、Asset serving/resolution、VersionGuard、ControlRequest、ExecutionEvent 最小 JSON Schema。
- [x] 2.3 覆盖 PRT/ONLINE、ONLINE stable/gray、第三 serving 版本、版本失配、控制去重与 Result 层级正反例。
- [x] 2.4 记录 Python/Runtime 打包建议和六域回交字段，不改根 manifest/lockfile。
- [x] 2.5 按 main-brain 审阅收敛 `ResultInterpretationPolicySet`、package-relative `logicalPath` 与单一 `skillKey`，不增加通用表达式引擎或字符串前缀解析。
- [x] 2.6 按独立 pre-merge review 修复非空/asset-unique 版本集、closed event + runSequence、policy/resource 语义唯一性和 Action 四事实片段。

## 3. VERIFY

- [x] 3.1 执行聚焦 Schema 检查并记录命令、Python/jsonschema 版本、case 数与输出。
- [ ] 3.2 执行 `git diff --check`、专属路径、来源和敏感信息检查。
- [ ] 3.3 更新 regression/readiness；保留未验证的 PostgreSQL、多实例、Runtime 和协议门禁。

## 4. DELIVER

- [x] 4.1 fetch/merge 最新 `origin/main`，只提交本 change 与 `packages/contracts/`。
- [x] 4.2 push worker，再通过独占 integration worktree 合入 `origin/main`。
- [x] 4.3 准备 main-brain handoff：实际文件、SHA、检查、剩余冲突与 `NO READY` 门禁。
