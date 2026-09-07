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
- 2026-09-07 多次 fetch/merge origin/main；修复前已消费 Skill registry 主干 `d60998e42b43805ae88bb10d2d1b1f2b3127a148`。
- Engine-first 主干：`f8ecc5bedc4804465f305a4dc8fcbe9d1523229f`；只继续 Python Deep Agent/Workflow Runtime，其他六域暂停。
- 所有未提交文件均在本任务 owned OpenSpec 与 `experiments/runtime-phase1/`；未触碰其他 owner 文件。

## 当前里程碑

- 状态：ENGINE_FIRST_SOURCE_STABILIZATION
- Runtime：NO READY
- 已完成：三 Tool engine spine、同步/异步 Finalizer、原始 args 闭合准入；真实 Skill Registry/fixture、synthetic Ability port 与 DISPLAY_ONLY Application 已贯通；PG 双进程 native-branch interrupt/resume/join 有界探针通过。
- TDD：Runtime 31/31 GREEN；engine 缺失 Finalizer 与 PG 最终 trace 串行顺序假设均先产生目标 RED，再以最小门禁/并行顺序断言修复。
- 已交付：准入修复 `ad102ab14957df40c098feef61a2c3e396b4f189` 与分支子图候选 `7a8fd6ca48556df17f51b937fb66e37db9236af3` 均已 push 并由独占 integration worktree 快进合入 `origin/main`；修复复审 Critical=0、Important=0。
- 新证据：平铺 RED 仍为 trace=`[B1]`；分支子图候选在 A interrupt 时 trace=`[B1,B2]` 且 join 未运行，已获准进入 PG 验证但不代表任意 DAG/恢复验收。
- 未完成：同 thread 并发冲突、修复后 bootstrap 现场 PG 复跑、A2UI-only retry、stop/restart、真实 Ability、live model 与生产 services/runtime。

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
- Runtime suite 31/31 GREEN；contracts Python 16/16、focused validator 57/57。
- PG-P1-01 启动前：Docker 26.1.3/x86_64/overlay2；available 821MiB、swap used 425MiB、磁盘可用 22GiB，目标 image/container/volume/task-dir 均不存在。
- yihaidao 专属资源已由 main-brain 按用户授权清理；MySQL 不再是 OpenSource 健康基线，本任务未恢复或使用 MySQL。
- 原 Docker Hub digest 两次因代理限流/EOF失败；用户批准 ECR mirror 的同一 linux/amd64 manifest digest 后首次 pull 成功，inspect 为 PostgreSQL 17.11。
- PG-P1-01：network=none、Ports={}、SCRAM-only、256MiB/no-extra-swap、0.5CPU、pids128、shm32MiB；非 superuser role limit=2，第三连接刻意实测拒绝并在 finally 关闭前两连接。
- process A 在 thread `pg-p1-native-parallel-20260907-02` 写入 trace=`[B1,B2]`、interrupt=1 后退出；独立 process B 读回 before=`[B1,B2]`，resume 后 trace=`[A_RESUMED,B1,B2,JOIN]`、interrupt=0。
- 首次 ad-hoc bootstrap 因 SQL literal 缺失把一次性 probe 密码写入隔离 PG 日志；该值视为暴露，不复用、不记录。最终 exact container/volume/private dir/image 已删除，不宣称 secure erase。
- 源码 bootstrap 已改为 libpq SCRAM verifier + NOLOGIN gate；失败确认 role disabled，否则 UNSAFE_UNKNOWN 并要求销毁隔离 PG，synthetic sentinel 3/3 GREEN；修复尚未现场 PG 重跑。

## Next Executable Action

停止扩展实现范围。下一步只对当前 engine-first 与 PG probe owned diff 执行 review/secret scan/完整验证，固定 worker source commit，随后从最新 origin/main 在独占 integration worktree 合入并 push；仍不实现第二 scheduler。

## 交付状态

- 首批源码：`1aa1410ca6ca9537507da776cd8d394c526f13b4`
- 原始参数准入修复：`ad102ab14957df40c098feef61a2c3e396b4f189`
- 并行 RED reproducer：`730331d0b91fb3ec98db5bae6c578c777edc5fcd`；显式执行 exit=1，expected `[B1,B2]` / actual `[B1]`
- 原生分支子图候选：`7a8fd6ca48556df17f51b937fb66e37db9236af3`；A interrupt、B2 完成、join 未运行
- Worker source push：PASS，源码 tip=`7a8fd6ca48556df17f51b937fb66e37db9236af3`
- Integration：PASS，feature tip `7a8fd6ca48556df17f51b937fb66e37db9236af3` 已合入 `origin/main`；本 checkpoint 记录提交在其后
- OpenSpec structure：PASS；CLI 在 PATH/仓库中均不可用，未在线安装替代
- Runtime readiness：NO READY
