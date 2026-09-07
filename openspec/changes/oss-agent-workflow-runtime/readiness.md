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
