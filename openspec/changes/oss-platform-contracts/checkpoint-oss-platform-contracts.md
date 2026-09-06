# Execution Checkpoint

- Updated at: 2026-09-07T01:57:56+08:00
- Thread: oss-platform-contracts
- Change: oss-platform-contracts
- Status: ACTIVE
- Current phase: VERIFYING
- Baseline: `SW-P1-20260907.2 + ENG-01`
- Candidate revision: `SW-CONTRACTS-P1-CANDIDATE.1`
- Scope: 公共契约候选、最小 JSON Schema/正反例和聚焦检查。
- Out of scope: Runtime/领域实现、根依赖、协议版本冻结、数据库/服务/部署/secret。

## Worktrees

| Repo | Worker path | Worker branch | Target branch | Base/HEAD | Dirty files |
| --- | --- | --- | --- | --- | --- |
| platform | `/home/admin/OpenSource/repos/.parallel/oss-platform-contracts/platform` | `codex/oss-platform-contracts/design` | `main` | `0980f0ae304a340f24d7421ab4a51818af612b32` | 本 change 7 文件；`packages/contracts/` 57 文件 |

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
- 环境为 Python 3.6.8/jsonschema 2.6.0；未安装依赖、未修改系统 Python。PY-01 已读，主机 Python 变更仅 Runtime 可执行。

## In Progress

- 正在执行 review 修复后的 fresh verification。

## Pending

- 更新最后验证证据并提交/push worker。
- 通过独占 integration worktree 合入最新 `origin/main`，再回传 main-brain。

## Next Executable Action

- 执行 Schema fresh check、JSON parse、`git diff --check`、独占路径和 clean-room 扫描。

## Blockers

- 无。Draft 4 只是当前免安装校验 dialect，不是最终依赖冻结；运行态门禁仍 NO READY。

## Last External Progress

- 2026-09-07T01:57:56+08:00：合入最新 main `0980f0ae304a340f24d7421ab4a51818af612b32`，fresh START 无 recorded versions 非回归后 54/54。
