# Execution Checkpoint

- Updated at: 2026-09-07T02:34:34+08:00
- Thread: oss-platform-contracts
- Change: oss-platform-contracts
- Status: IMPLEMENTING / APPROVED SUBSET
- Current phase: BUILD_VERIFY
- Baseline: `SW-P1-20260907.2 + ENG-01`
- Candidate revision: `SW-CONTRACTS-P1-CANDIDATE.1`
- Scope: 公共契约候选，以及 `SW-P1-SUBSET-01` 批准的 Skill/Policy 薄 Python adapter。
- Out of scope: Runtime/领域实现、根依赖、协议版本冻结、数据库/服务/部署/secret。

## Worktrees

| Repo | Worker path | Worker branch | Target branch | Base/HEAD | Dirty files |
| --- | --- | --- | --- | --- | --- |
| platform worker | `/home/admin/OpenSource/repos/.parallel/oss-platform-contracts/platform` | `codex/oss-platform-contracts/design` | `main` | `3a48d4b106db8f382c3c96bbc8992f328b81e259` | `packages/contracts/`、本 change 文档 |
| platform integration | `/home/admin/OpenSource/repos/.integration/oss-platform-contracts/platform` | `codex/integrate/oss-platform-contracts/design` | `main` | 待交付前刷新 | 待核验 |

## Completed With Evidence

- linked worker 已从旧设计安全 fast-forward 到 `SW-P1-20260907.2` 集成 SHA `c168f2c3b7f86cb0bd5e2bec48caf4ec1de1df7e`；未触碰其他任务 checkpoint。
- 提交前再次 fetch/merge `origin/main` 到 `0980f0ae304a340f24d7421ab4a51818af612b32`；ENG-01、数字员工、Capability、A2UI、Workflow 入站文件与本线程专属路径无重叠。
- 已读取 `engineering-decisions.md` 的 ENG-01：公共治理允许中立 Schema + 薄 Python adapter，但不授权本任务改系统 Python、根 manifest/lock 或创建未批准依赖。
- Runtime 回传实测 Python 3.11.13/Pydantic 2.13.5；建议包范围 Python `>=3.11,<4`、可选 Pydantic `>=2.13,<3`，并保持 Deep Agents/LangGraph/PostgreSQL/Runtime adapter 零依赖。
- active OpenSpec 已移除 preview/stable、workspaceId/issuer、frozen continuation、业务幂等和协议预冻结冲突。
- 已向 main-brain 回传两次对齐/字段进展，并收到继续 candidate Schema 的确认。
- 已读取 main-brain 明确放行的 Skill consumer inputs（仅 inputs/，不含 checkpoint），并与 A2UI、Runtime 直接同步字段。
- candidate 覆盖 TrustedContext、serving/publication、resolution、VersionGuard、ControlRequest、ResultInterpretationPolicy、execution refs/events、use_skill content+artifact。
- main-brain 审阅要求已纳入：材料 handle 使用规范化 package-relative `logicalPath`；结果解释只保留 `SCHEMA_VALID` / `JSON_POINTER_EQUALS` 和唯一 Runtime 解释器语义；Capability 容器为 `resultInterpretationPolicies + defaultSuccessPolicyRef`。
- 独立 pre-merge review 发现并已修复：空/冲突 recorded versions、event 交叉归因/外来事实、policy 默认/唯一性、Action 四事实、材料重复路径/换行边界和状态措辞。
- TDD 七轮 RED/GREEN 加 fresh START 非回归检查完成；最终命令 `python3 packages/contracts/tests/validate_contracts.py` 为 `SUMMARY total=54 passed=54 failed=0`。
- candidate 内容已提交并 push worker：`404bbcacc1ef176c273c9a90fc4ae91bfadc42fd`。
- checkpoint 里程碑提交后最终 worker 为 `f8cf77baf8fd2663ea06bcb1cfc25135f08ca4fb`。
- 独占 integration worktree 从最新 main `a4915ad6ad5e6a847c8ac6309590601f7875ccd8` 合入 worker，复跑 54/54、55 JSON、64 文件 scope/diff 检查后 push main `05cab8bd33ca89c392b21aa8be2fe8250fd696e2`。
- main-brain subset probe 发现 Draft 4 `$` 的终末换行边界；新增 3 个负例得到 RED 57/54/3，并仅给 identifier/skillKey 加 CR/LF 排除后 GREEN 57/57。
- final regex delta 内容 commit `a1cb44e88ce5bb603c62b4618804c78ae0d5585c` 已 push worker 并 fast-forward 集成到 main；integration fresh check 为 57/57、58 JSON、专属 scope PASS。
- 环境为 Python 3.6.8/jsonschema 2.6.0；未安装依赖、未修改系统 Python。PY-01 已读，主机 Python 变更仅 Runtime 可执行。
- `implementation-release-01.md` 已完整读取并校验：65 行，SHA256 `c14eb61371562bf512b393ab347c80d2c4e3be082e4a7e838dc13e2a0f9743a4`。
- worker 已 fetch 并 fast-forward merge 最新 `origin/main` 到 `3a48d4b106db8f382c3c96bbc8992f328b81e259`。
- Python 3.11 薄 adapter 完成首轮 TDD：缺包时 RED，严格模型/schema loader/显式 dispatcher 落地后 13/13 GREEN；未安装依赖。
- fresh verification：Python 3.11 import smoke PASS、adapter 13/13、批准闭包既有 fixture 25/25 对照、Draft 4 全量 schema 57/57；测试生成的两个 task-owned `__pycache__` 已删除。
- 首轮内容 commit `cc20e510e13b26e42943997332e1319c509d1001` 后独立 review 为 `With fixes`：无 Critical，发现异常 issues 可改写和复合 schema `$ref` 悬空两项 Important；main-brain 另实证 Workflow 显式 `conversationId:null` 与缺省混同。
- 三项均完成 TDD：16 total / 12 PASS / 4 FAIL 后最小修复为 16/16 GREEN；同时补充非有限 JSON number 与 dispatcher allowlist probe。

## In Progress

- 对 review 修复 delta 做独立复审和 fresh 全量门禁。

## Pending

- 完成修复 delta 的独立复审和精确 diff 终检。
- commit/push worker 并通过独占 integration worktree合入最新 `origin/main`。

## Next Executable Action

- 提交 review 修复 delta，并请求 reviewer 复核三项证据。

## Blockers

- 源码实现无阻塞。运行态 PostgreSQL/多实例/ingress/event/SDK 证据仍是 `NO READY` 门禁。

## Last External Progress

- 2026-09-07T02:34:34+08:00：三项 review delta 完成 RED/GREEN，adapter 16/16 GREEN。
