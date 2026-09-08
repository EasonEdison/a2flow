# oss-agent-workflow-runtime 执行检查点

## 身份与所有权

- 任务标题：oss-agent-workflow-runtime
- Worker：/home/admin/OpenSource/repos/.parallel/oss-agent-workflow-runtime/platform
- 分支：codex/oss-agent-workflow-runtime/design
- 集成目标：origin/main
- 独占规格：openspec/changes/oss-agent-workflow-runtime/
- 预留实验：experiments/runtime-phase1/
- 本次授权实现：services/agent-workflow-runtime/（AF-RUNTIME-03）
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

- 状态：AF_RUNTIME_03_PG_W1_ACCEPTED_DOC_REVIEW
- 当前基线：87e17e7322f3932e0e84e2caa501a92bfcf10465；AF-RUNTIME-03 release 已读取，保留 owned WIP 时 fast-forward merge，无 Git 冲突。
- 前批源码：0e73d8b 已服务器集成；GitHub 同步由 main-brain 完成。
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

AF-RUNTIME-03 固定660db6a已完成单次PG-W1，9/9真实用例通过且精确清理。提交own证据文档并交主控验收；未释放前不集成server main/GitHub，不再启动PG。

## 交付状态

- 首批源码：`1aa1410ca6ca9537507da776cd8d394c526f13b4`
- 原始参数准入修复：`ad102ab14957df40c098feef61a2c3e396b4f189`
- 并行 RED reproducer：`730331d0b91fb3ec98db5bae6c578c777edc5fcd`；显式执行 exit=1，expected `[B1,B2]` / actual `[B1]`
- 原生分支子图候选：`7a8fd6ca48556df17f51b937fb66e37db9236af3`；A interrupt、B2 完成、join 未运行
- Worker source push：PASS，源码 tip=`7a8fd6ca48556df17f51b937fb66e37db9236af3`
- Integration：PASS，feature tip `7a8fd6ca48556df17f51b937fb66e37db9236af3` 已合入 `origin/main`；本 checkpoint 记录提交在其后
- OpenSpec structure：PASS；CLI 在 PATH/仓库中均不可用，未在线安装替代
- Runtime readiness：NO READY

- AF-RUNTIME-02 当前切片：内部 Action admission/executor/policy/completion + native LangGraph adapter + Finalizer guard；worker 提交 SHA 以本记录所在源码提交及回执为准。

## AF-RUNTIME-03 新进展

- 两表持久化、schemaVersion=1 闭合序列化、owner 显式 get、独立 save commit 与两类 session 锁已落盘。
- 主控批准最小 run 在途/未确认 gate；不新增恢复/接管/调度。
- 主控 WIP finding：伪完成记录无成功 Attempt 可越过 Finalizer；已补一致性校验与负例。
- PG 用例包括同步 PostgresSaver 和真实图在锁丢失后仍可完成的限制验证；尚未执行。
- 受控脚本 exact targets：a2flow-runtime03-pg / a2flow-runtime03-pgdata / /home/admin/OpenSource/.tmp/af-runtime-03-pg。
- 待审脚本提供 finally 清理、role limit8/server16、5ms 连接观测、15min/resource 限制；--help 只读通过。
- 所有当前新增文件 admin-owned；无新包/HTTP/根 Compose/共享契约修改。

- AF-RUNTIME-03 窗口审查补充：显式禁用 LangSmith/LangChain tracing；独有 window marker + UID/group/session 验证后仅清理本脚本进程组；无论 parent 退出、killpg 竞态或双超时，finally 都执行日志检查和精确资源清理。模拟 PG-owned socket 权限失败已验证仅针对 PRIVATE/socket 的 sudo 删除，以及残留显式失败。docker logs 在清理前仅做本次两个 secret 的内存 substring 检查，只输出 PASS/FAIL。6 个离线故障测试通过，PG 仍未运行。

## PG-W1 单次完成回执

- 固定源码660db6a7dffe0c6f270f3e0c84767aab36d87f70；hash103e9dcd2b36767bbf1483d84d57605928cc9ade2a5f6870080d284b2cdcfc1b。
- 9/9 PASS，87.651s；window105.14s含pull；无窗口中源码修改、无重跑。
- peakConnections4（5ms含observer）、minAvailable1039332KiB、swapGrowth0、data49792KiB。
- 凭据日志检查PASS；收尾runtime sessions0/advisorylocks0；exactcontainer/volume/private目录/新拉镜像均删除。
- 独立复核目录不存在、筛选无container/volume、5432无监听；无关pause镜像保留；空.tmp父目录保留。
- 9项实际断言与局限已写regression/readiness；主控已接受有界PG结果，等待文档review与独立集成令。
