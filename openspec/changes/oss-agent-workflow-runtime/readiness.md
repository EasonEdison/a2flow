# Agent/Workflow Runtime Phase 1 Readiness

## 总结

- 当前结论：NO READY
- Phase 1 基线：ALIGNED
- `SW-P1-SUBSET-01`：APPROVED_AND_CONSUMED（仅 use_skill/trusted-context 命名闭包）
- SDK 版本/API：RESOLVED_AND_IMPORTED
- 实验代码：PARTIAL，21 个当前用例 GREEN
- Provider wire：OFFLINE_VERIFIED；live model 未验证
- PostgreSQL：IMAGE_PULL_BLOCKED；未 provision
- 双进程：NOT VERIFIED
- 独立并行：STRUCTURAL_CANDIDATE_ONLY；retry/stop/restart：NOT VERIFIED
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
| A2UI | PARTIAL | DISPLAY_ONLY 与 INTERACTIVE interrupt payload 通过；Action resume/success/completion/Finalizer 未通过 |
| 并行映射 | PARTIAL_CANDIDATE | 每分支 compiled subgraph 候选获准进入 PG 验证；平铺反例仍只到 B1，任意 DAG/恢复未验收，且不得补第二 scheduler |
| retry/stop/restart | NO READY | 仅 A2UI retry；stop 不可 resume；restart fresh |
| PostgreSQL | NO READY | AsyncPostgresSaver + migration + process restart |
| 多进程 | NO READY | 两个 stateless process 共享 PG 的查询/resume/冲突证据 |
| 安全与 clean-room | PARTIAL | 合成 fixture、无真实 key/业务数据/网络；最终 secret/license/source scan 待执行 |

## 当前环境阻塞

PY-01 已完成：DNF transaction 9 仅新增 7 个 Python 3.11 相关包；`/usr/bin/python3.11` 为 3.11.13，而默认 `/usr/bin/python3` 仍为 platform-python 3.6.8。安装后 DNF 4.7.0 与 tuned active 均正常。

Task-owned venv 已解析并导入 Deep Agents/LangGraph/PostgreSQL checkpointer，`pip check` 无 broken requirements。PG-P1-01 已批准为 network-none/Unix-socket-only，但固定官方 digest 的两次 180 秒拉取均被现有镜像代理限流并以 EOF/context canceled 结束；没有 image/container/volume/secret 遗留。不得自行第三次重试、换源、操作 main-brain 正在清理的 yihaidao 专属资源、引入 MySQL、公开端口或真实 key。

## 已撤销门禁

以下旧门禁不再要求，也不得回流：

- TypeScript/LangGraphJS 选型 spike；
- Runtime 外部业务 exactly-once、lease/fencing 通用 scheduler；
- 通用 Skill recovery/retry；
- frozen old revision continuation；
- restart reconciliation 或跨 run dedup。

## READY 更新规则

只有 main-brain 审查全部实验 diff、真实命令输出和 PostgreSQL/双进程证据后，才可调整本文件。完成 tasks 比例或 Git merge 不自动改变 NO READY。
