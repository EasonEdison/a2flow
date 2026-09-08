# Agent/Workflow Runtime Phase 1 Readiness

## 总结

- 当前结论：NO READY
- Phase 1 基线：ALIGNED
- `SW-P1-SUBSET-01`：APPROVED_AND_CONSUMED（仅 use_skill/trusted-context 命名闭包）
- SDK 版本/API：RESOLVED_AND_IMPORTED
- 实验代码：PARTIAL，31 个当前用例 GREEN
- Provider wire：OFFLINE_VERIFIED；live model 未验证
- PostgreSQL：BOUNDED_FUNCTIONAL_PASS_WITH_SECURITY_FINDING；临时环境已清理
- 双进程：BOUNDED_SYNTHETIC_PASS；并发冲突未验证
- 独立并行：PG_VERIFIED_CANDIDATE；retry/stop/restart：NOT VERIFIED
- 产品 Runtime：NOT IMPLEMENTED
- 部署：NOT AUTHORIZED

本 change 合入只代表设计/实验源交付，不代表 SDK 可运行、Runtime 可用或产品完成。

## 门禁

| 门禁 | 状态 | 通过条件 |
| --- | --- | --- |
| Python 运行时 | PASS | Python 3.11.13 并行安装完成；默认 3.6.8、DNF 与 tuned 复核正常 |
| 依赖锁定 | PARTIAL | resolver/import/pip-check/59 项实验 lock 已完成；`psycopg-binary` LGPL notice/分发评审未完成 |
| 共享契约 | PARTIAL | `SW-P1-SUBSET-01` 已批准并消费；bundle 其余定义仍 provisional |
| Tool-only Skill | PARTIAL | model schema/trusted context/provider wire 与注入前原始 args 闭合准入已通过；Workflow 入口和产品级 mandatory admission 未证明 |
| Deep Agents Tool surface | PASS_FOR_PROBE | 模型只绑定 Runtime-owned Tool；默认文件/shell/subagent Tool 全部排除 |
| A2UI | PARTIAL | DISPLAY_ONLY 与 INTERACTIVE interrupt payload 通过；engine Finalizer 成功/提前结束门禁通过，Action resume/success/completion 未通过 |
| 并行映射 | PARTIAL_CANDIDATE | 单一 synthetic native branch 已用 PG 双进程验证；平铺反例仍只到 B1，任意 DAG/冲突未验收，且不得补第二 scheduler |
| retry/stop/restart | NO READY | 仅 A2UI retry；stop 不可 resume；restart fresh |
| PostgreSQL | PARTIAL | AsyncPostgresSaver setup、进程退出后读回/resume 已通过；产品 migration、并发冲突与修复后 bootstrap 现场复跑未完成 |
| 多进程 | PARTIAL | 两个串行 stateless process 共享 PG 的查询/resume/join 已通过；同 thread 并发冲突未验证 |
| 安全与 clean-room | PARTIAL | synthetic/scripted、无业务数据/公网端口；首次临时密码进入隔离 PG 日志为 finding，最终 secret/license/source scan 待执行 |

## 当前环境阻塞

PY-01 已完成：DNF transaction 9 仅新增 7 个 Python 3.11 相关包；`/usr/bin/python3.11` 为 3.11.13，而默认 `/usr/bin/python3` 仍为 platform-python 3.6.8。安装后 DNF 4.7.0 与 tuned active 均正常。

Task-owned venv 已解析并导入 Deep Agents/LangGraph/PostgreSQL checkpointer，`pip check` 无 broken requirements。原 Docker Hub digest 两次受代理限流/EOF 阻塞后，经用户批准使用同一 linux/amd64 manifest digest 的 ECR mirror；首次 pull 成功，PostgreSQL 17.11 在 network-none、Unix-socket-only、SCRAM-only 和资源限额下完成 AsyncPostgresSaver 双进程探针。process A 退出时持久化 `B1,B2 + interrupt`；独立 process B 读回并 resume 到 `A_RESUMED,B1,B2,JOIN`。首次 ad-hoc bootstrap 的 SQL literal 缺失使一次性临时 probe 密码进入隔离 PG 日志，该值视为暴露；最终 container/volume/private dir/image 已精确删除，但不宣称 secure erase。源码现用 libpq 生成 SCRAM verifier，role 在完整成功前保持 NOLOGIN；失败时确认禁用，否则标记 UNSAFE_UNKNOWN 并要求销毁隔离 PG，3 个 sentinel 负例通过；修复尚未现场 PG 重跑。

## 已撤销门禁

以下旧门禁不再要求，也不得回流：

- TypeScript/LangGraphJS 选型 spike；
- Runtime 外部业务 exactly-once、lease/fencing 通用 scheduler；
- 通用 Skill recovery/retry；
- frozen old revision continuation；
- restart reconciliation 或跨 run dedup。

## READY 更新规则

只有 main-brain 审查全部实验 diff、真实命令输出和 PostgreSQL/双进程证据后，才可调整本文件。完成 tasks 比例或 Git merge 不自动改变 NO READY。

## AF-RUNTIME-02 更新 — 2026-09-08

- 内部 Action 服务：SOURCE_CANDIDATE；24/24 新离线用例 GREEN，旧实验 31/31 GREEN。
- 真实 Deep Agent assembly：节点绑定交互、可信完成引用、原 Skill 证据跨 resume 保留、同步/异步 Finalizer 拒绝待交互、双卡隔离通过。
- 控制去重与 continuation 状态有记录；测试端口锁与 MemorySaver 不证明 PG 或多实例安全。
- PG Action 存储、async continuation/executor、恢复重试、完整 stop/restart、HTTP/产品/部署仍未实现或验证。
- 本切片仅 worker 交付；等待 main-brain 审查后释放 server main 集成。Runtime 仍 NO READY。

## AF-RUNTIME-03 当前状态 — 2026-09-08

- 源码：IMPLEMENTED_PENDING_REVIEW；PostgreSQL Action repository/控制表、短独立提交、session 锁和显式 owner 查询已实现。
- 离线：38 PASS；9 PG SKIPPED；实验 37 PASS（既有 31 + 窗口故障 6）。修复主控发现的完成引用跨字段校验漏洞。
- PostgreSQL Action/多进程：NOT RUN；不得借用旧 PG-P1-01 异步探针证据宣布本切片通过。
- 窗口：NOT AUTHORIZED；受控脚本已提供，尚未启动 PG 或创建一次性凭据。
- 语义边界：EXECUTING/EXECUTION_UNCONFIRMED/DISPATCHING/UNCONFIRMED 阻止同 run 新控制，
  相同控制只读历史；DISPATCHING 可能健康在途，不确定不等于失败；门禁不自动接管/恢复。
- 锁限制：session 失连不能撤销在途 executor/graph，不保证在途图全生命周期排他。
  活性检查与外部副作用非原子；失连后不补写 RETURNED，历史 DISPATCHING/EXECUTING 不重派发。
- 无生产 Compose、HTTP、live model、async Action、完整 stop/restart、业务 exactly-once 或恢复调度器。
- 当前源码尚未集成 server main；Runtime 仍 NO READY。

- AF-RUNTIME-03 窗口审查补充：显式禁用 LangSmith/LangChain tracing；独有 window marker + UID/group/session 验证后仅清理本脚本进程组；无论 parent 退出、killpg 竞态或双超时，finally 都执行日志检查和精确资源清理。模拟 PG-owned socket 权限失败已验证仅针对 PRIVATE/socket 的 sudo 删除，以及残留显式失败。docker logs 在清理前仅做本次两个 secret 的内存 substring 检查，只输出 PASS/FAIL。6 个离线故障测试通过，PG 仍未运行。

## AF-RUNTIME-03-PG-W1 窗口后更新 — 2026-09-08

- PG Action/跨进程：BOUNDED_SYNTHETIC_PASS_ACCEPTED_BY_MAIN，9/9，固定660db6a；完整Runtime仍NO READY。
- 真实同步PostgresSaver跨进程Skill/交互/Action/native resume/Finalizer及已完成B不重放已通过。
- EXECUTING/未确认不重派发、独立连接可见已提交reservation、同请求竞争和多卡更新均有PG证据。
- 在途图失去continuation session后仍可JOIN，证明其不可撤回限制；未将其宣称全生命周期排他。
- 本轮SCRAM verifier bootstrap现场执行；两枚本轮明文secret对exact容器日志检查PASS，闭合该修复的本窗口有界证据。
- 连接观测峰值4，minAvailable1039332KiB，swap增长0，data49792KiB；收尾sessions0/locks0。
- 窗口已关闭：container/volume/private dir/本次新拉镜像已删除，5432无监听；不宣称secure erase。
- 无新窗口、生产Compose/HTTP/live model/自动恢复或server main/GitHub集成授权。

- main-brain 已接受本次有界PG结果；当前仅待证据文档提交review和server main集成令，产品NO READY不变。
