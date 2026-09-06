# oss-agent-workflow-runtime 执行检查点

## 身份与所有权

- 任务标题：oss-agent-workflow-runtime
- Worker：/home/admin/OpenSource/repos/.parallel/oss-agent-workflow-runtime/platform
- 分支：codex/oss-agent-workflow-runtime/design
- 集成目标：origin/main
- 独占规格：openspec/changes/oss-agent-workflow-runtime/
- 预留实验：experiments/runtime-phase1/
- 预留实现：services/runtime/
- 禁止：其他任务 checkpoint、共享根文件/依赖/版本、部署、secret、现有服务/数据库/端口；Python 仅按 PY-01 单执行者边界变更

## 基线真值

- 基线 ID：SW-P1-20260907.2
- 基线提交：1bcc61a4137436f5c3811d555d2af8244c0fc971
- 工程批准子集：`SW-P1-SUBSET-01`；release SHA256 `c14eb61371562bf512b393ab347c80d2c4e3be082e4a7e838dc13e2a0f9743a4`。
- 2026-09-07 已核对 linked worktree、branch、status、worktree list。
- 2026-09-07 多次 fetch/merge origin/main；本里程碑已合入 `28dde023e323c4fa4f9f509b9f6e3954bc669b7a`。
- 所有未提交文件均在本任务 owned OpenSpec 与 `experiments/runtime-phase1/`；未触碰其他 owner 文件。

## 当前里程碑

- 状态：PHASE1_PARALLEL_PROGRESSION_RED_RECORDED
- Runtime：NO READY
- 已完成：PY-01 安装/健康复核；task venv；SDK resolver/import；59 项实验 lock；主干 `skillweave_contracts` 严格适配；真实 Skill fixture；Deep Agent Tool surface；离线 Anthropic wire；A2UI mode/interrupt。
- TDD：首批 15/15 GREEN；有效 RED 包括默认隐式 Tool 暴露、provider schema 非 strict/非批准 pattern、newline key、非法 resolver result 与 Interaction 碰撞。
- 已交付：worker/source commit `1aa1410ca6ca9537507da776cd8d394c526f13b4` 已 push，并由独占 integration worktree 快进合入 `origin/main`；独立 reviewer 已批准（Critical=0，Important=0）。
- 新证据：显式 RED reproducer 在 LangGraph 1.2.11 观测到 A interrupt 时 trace 只有 `[B1]`，B2 未进入下一 superstep，join 未运行；未实现 fallback scheduler。
- 未完成：独立并行 B1→B2 GREEN、PostgreSQL setup、双进程 resume、A2UI-only retry、stop/restart、生产 services/runtime。

## 移除的冲突

- TypeScript/LangGraphJS 选型与 parity spike。
- Runtime 业务幂等、跨 run dedup/补偿、通用 lease/fencing scheduler。
- 通用 Skill retry/recovery、冻结旧版本续跑、固定 Skill 子图。
- presentation 即暂停、Action success 即完成、Finalizer 越界。
- thread_id 可证明独立并行推进的假设。

## 环境证据

- DNF transaction 9：只新增 Python 3.11.13/pip 及相关 7 包；0 update/remove。
- 默认 `/usr/bin/python3` 仍为 platform-python 3.6.8；`/usr/bin/python3.11` 为 3.11.13。
- 安装后 DNF 4.7.0、tuned active；现有系统工具/服务未改解释器。
- venv：`/home/admin/OpenSource/.venvs/skillweave-runtime-p1`，admin-owned。
- deepagents 0.7.13、langchain 1.4.0、langchain-core 1.6.2、langgraph 1.2.11、checkpoint-postgres 3.1.2。
- `langgraph==1.2.10` 首次 resolver 因 LangChain 要求 >=1.2.11 被拒；未锁入。
- `AsyncPostgresSaver` 首次 import 因无 libpq implementation 失败；加入 venv-only psycopg-binary 3.3.5 后通过。
- `pip check` 无 broken requirements；`requirements.lock` 59 项。
- psycopg-binary metadata 为 LGPL-3.0-only；正式分发/notice 评审未完成。
- `SW-P1-SUBSET-01` 共享相关 fixtures 15 个全部匹配主干共享严格适配；全 bundle focused validator 57/57。
- Runtime suite 首批 15/15 GREEN。
- 未启动 PostgreSQL/容器/公开服务，未触碰现有 MySQL 或真实 key。

## Next Executable Action

提交并回传 A 等待/B1→B2 的显式 RED reproducer 与实际 assertion；等待 main-brain 对并行执行模型裁决。不得自建第二 scheduler；PostgreSQL/双进程继续等待明确协调，不以其他 saver 替代。

## 交付状态

- 已交付源码：`1aa1410ca6ca9537507da776cd8d394c526f13b4`
- 并行 RED reproducer：未提交
- Worker push：PASS，远端 worker 包含 source commit 与 checkpoint commit `9238e2fbcd811ab74f6dbb80cb3accc7bb367e49`
- Integration：PASS，`origin/main` 包含 source commit `1aa1410ca6ca9537507da776cd8d394c526f13b4` 与 checkpoint commit `9238e2fbcd811ab74f6dbb80cb3accc7bb367e49`
- OpenSpec structure：PASS；CLI 在 PATH/仓库中均不可用，未在线安装替代
- Runtime readiness：NO READY
