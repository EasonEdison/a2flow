# Agent/Workflow Runtime Phase 1 回归与证据

## 当前结论

- 回归状态：PARTIAL
- Runtime：NO READY
- SDK 行为用例：31/31 GREEN（含 engine spine、credential-safety 与原生 compiled subgraph 候选）
- 共享 contracts focused validator：57/57 GREEN；只代表 shape/fixture
- 当前完成：Python 3.11 隔离环境、依赖解析/import、`SW-P1-SUBSET-01` 对齐、真实 Skill fixture、离线 Anthropic wire、A2UI mode/interrupt、三 Tool engine spine、Finalizer、原始参数准入与 PG 双进程 native-branch 探针
- 当前阻塞：产品 Runtime、A2UI-only retry、stop/restart、同 thread 并发冲突与 live model 尚未验证；修复后的 secret-safe bootstrap 未现场 PG 重跑

## 已执行环境证据

| 检查 | 命令 | 实际输出 | 结论 |
| --- | --- | --- | --- |
| Worker 主干 | `git rev-parse HEAD` after merge | `28dde023e323c4fa4f9f509b9f6e3954bc669b7a` | 已消费 `SW-P1-SUBSET-01` release 与 schema snapshot |
| PY-01 安装 | DNF transaction 9 | 新增 python3.11 3.11.13、pip 22.3.1 等 7 包；无 update/remove | 已按批准精确事务完成 |
| 系统解释器 | `python3 --version` / `/usr/bin/python3.11 --version` | 3.6.8 / 3.11.13 | 默认 platform-python 未替换 |
| 系统健康 | `dnf --version` / `systemctl is-active tuned` | 4.7.0 / active | 安装后系统工具与 tuned 正常 |
| task venv | `/home/admin/OpenSource/.venvs/skillweave-runtime-p1` | admin-owned；Python 3.11.13 | 未污染系统 Python 包 |
| 首次 resolver | pin `langgraph==1.2.10` | `ResolutionImpossible`；LangChain 1.4.0 要求 >=1.2.11 | 1.2.10 未被错误锁定 |
| 最终 resolver/import | 1.2.11 + `AsyncPostgresSaver` import | deepagents 0.7.13、langchain 1.4.0、langgraph 1.2.11、checkpoint-postgres 3.1.2 | SDK/API import 通过 |
| Psycopg 实现 | 首次 import / 加入 `psycopg-binary==3.3.5` | 首次无 libpq implementation；binary wheel 后通过 | 不改系统 libpq；LGPL-3.0-only 仍是发布门禁 |
| 依赖一致性 | `python -m pip check` | `No broken requirements found.` | task venv 依赖闭包一致 |
| 依赖冻结 | `python -m pip freeze` | `requirements.lock` 共 59 项 | 仅实验锁；根 lock 未修改 |
| Release 记录 | SHA256 `implementation-release-01.md` | `c14eb61371562bf512b393ab347c80d2c4e3be082e4a7e838dc13e2a0f9743a4` | 使用获批 `SW-P1-SUBSET-01` 闭包 |
| Contracts Python adapter | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/contracts/src ... -m unittest discover -s packages/contracts/tests/python -v` | `Ran 16 tests ... OK` | 共享薄包 strict parse/serialize 通过 |
| Contracts fixture | `python3 packages/contracts/tests/validate_contracts.py` | `SUMMARY total=57 passed=57 failed=0` | 只证明 shared shape/fixture |
| Skill fixture | `sha256sum .../evidence-first-brief/SKILL.md` | `1cc034c1d066b24771e9b0d91bc74abd89012268cf225802c25dd33316e06434` | Runtime 测试读取主干真实 package bytes |
| Runtime suite | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/contracts/src:services/skill-registry/src:services/capability-registry/src:experiments/runtime-phase1 ... -m unittest discover ... -v` | `Ran 31 tests ... OK` | SDK/Tool/A2UI/provider-wire、engine spine、credential-safety、参数准入与原生分支子图候选通过 |
| PG image/runtime | approved ECR mirror, exact amd64 digest | PostgreSQL 17.11；network=none；Ports={}；256MiB/no-extra-swap；0.5CPU；pids128；shm32MiB；HBA 全 SCRAM | 无 TCP publish/trust；非 superuser role connection limit=2，第三连接实际拒绝 |
| PG process A | `postgres_parallel_probe A`，thread=`pg-p1-native-parallel-20260907-02` | `after=[B1,B2]`、interrupt=1、exit=0 | sibling branch 在 A wait 时完成 B2，join 未运行 |
| PG process B | 独立 `postgres_parallel_probe B`，同 thread | `before=[B1,B2]`；`after=[A_RESUMED,B1,B2,JOIN]`；interrupt=0、exit=0 | 进程退出后读回、合法 resume、父 join 通过；并行 reducer 顺序不作串行保证 |
| PG cleanup | exact container/volume/private dir/image removal | 运行约 4m30s；收尾 37.52MiB/6 PIDs/55.95MB；删除后 5432 无监听 | synthetic 数据与一次性 secret/log 随资源删除，不宣称 secure erase |

## 计划行为场景

下列 method 名是实验适配名，不是已批准共享协议。

| ID | Method | Params | 期望 data / interrupt / error | 字段级断言 |
| --- | --- | --- | --- | --- |
| P1 | DeepAgent.invoke(chat) / WorkflowSkillNode.invoke | `skillKey`、trusted invocation context | Tool trace + final result | 两个入口都先出现 use_skill；Skill fixture 无 Workflow 专用字段；当前仅 chat probe 已执行 |
| P2 | RuntimeTool.use_skill | model args 仅 `{skillKey}`；context 为获批 nested shape | result=`{contractRevision,content,artifact}` | Tool schema 无 userId/environment/versionId；请求/结果 Skill 与环境必须匹配 |
| P3 | VersionAdmissionGuard.check | recordedVersions、effectiveVersions、ingress | data={admitted:true} 或 error={code:RESET_REQUIRED} | start/continue/Action 都检查；不匹配前没有新业务 Tool |
| P4 | RuntimeTool.render_application | mode=DISPLAY_ONLY | data={rendered:true,mode,interaction:null} | 不产生 interrupt；同 branch 可继续 |
| P5 | RuntimeTool.render_application + Command(resume) | mode=INTERACTIVE、nodeId、interactionId、Action result | interrupt 或 data={businessSuccess,interactionCompleted} | 只有匹配 node/interaction/version 的 Action 可续跑；success/completion 分离；Finalizer 不越过等待 |
| P6 | WorkflowGraph.invoke/stream | A wait，B1、B2、join | state/events/checkpoint | A 未 resume 时 B1、B2 完成；join 未完成；thread_id 不被当锁或 branch selector |
| P7 | A2UIRetryPolicy.apply | render/Action failure、Skill/ability failure | data={retryOwnerNodeId,retryCount} 或 error | 只重试 A2UI owning node；已完成 predecessor/branch 不重放；其他失败不 retry |
| P8 | StopRun / RestartRun | stopped run、旧 interaction、fresh start | data={stopped:true} / data={newRunId,fresh:true} | stop 后无新工作且不可 resume；旧 card 拒绝；restart 不继承或核对旧业务结果 |

## 首批实际行为证据

| Method | Params | 实际 data / wire / interrupt | 字段级断言 |
| --- | --- | --- | --- |
| `RuntimeTool.use_skill` via ToolNode | model args=`{skillKey}`；trusted `TrustedInvocationContext` | ToolMessage `content` + server `artifact` | schema 只见 skillKey；userId/environment/versionId spoof 全部 error 且 resolver 0 次 |
| `skillweave_contracts.UseSkillResult.from_mapping` | `SW-P1-SUBSET-01` 15 个相关 shared fixtures | valid 通过、invalid 抛 ContractValidationError | extra/type、CR/LF、resource path、PRT/ONLINE selection 与 logicalPath 唯一性保持 |
| `DeepAgent.invoke` scripted | use_skill Tool call + trusted conversation context | final=`Completed from authorized Skill material.` | resolver 收到后端 context；model ToolMessage 只含 content |
| Deep Agents Harness Profile | 默认 SDK implicit Tool 集合 | bound tools=`{use_skill}` | `ls/read/write/edit/delete/glob/grep/task/execute` 均不暴露 |
| Anthropic provider serialization | 两轮离线 Messages API，经 `StrictToolChatAnthropic` | 第二请求含 tool_result content | wire schema `additionalProperties=false` 且 skillKey pattern 等于批准 schema；请求 JSON 无 artifact/evidenceRef |
| `render_application` DISPLAY_ONLY | integrated display fixture + Workflow context | `{rendered:true, interactionMode:DISPLAY_ONLY, interaction:null}` | 无 `__interrupt__` |
| `render_application` INTERACTIVE | integrated interactive fixture + trusted run/node | `A2UI_INTERACTION_REQUIRED` interrupt | runId、nodeId、application/version、tool-call identity 均参与绑定；同 node 两次 render 不碰撞；ordinaryChatMayResume=false |
| LangGraph parallel wait RED | A interrupt 与 B1→B2 平行，join 等待 A | assertion expected trace=`[B1,B2]`，actual=`[B1]` | interrupt 使单次 invoke 在当前 superstep 后返回；B2 未推进，join 未运行；未实现 fallback scheduler |
| Tool 原始参数准入 | 模型原始 args 含保留 `runtime` 字段 | status=`error`；Skill/Application resolver 均 0 次 | 使用公开 `wrap_tool_call` / middleware 扩展点，在 ToolRuntime 注入剥离保留字段前按闭合模型契约拒绝；可信 context 未被模型覆盖 |
| Deep Agent async 准入 | `ainvoke` 合法/保留 `runtime` 两类调用与异步 handler `Command` | 合法 resolver 1 次；恶意 resolver 0 次且 status=`error`；`Command` identity 保持 | `awrap_tool_call` 与同步路径复用同一原始 args 校验；基类 `NotImplementedError` RED 已修复 |
| LangGraph branch-subgraph candidate | 父图同轮并行 A/B 两个不同 compiled subgraph；B 内 B1→B2；父图 join | A interrupt；trace=`[B1,B2]`；无 `JOIN` | 按[官方 subgraph 公共接口](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)将共享 state 的 compiled subgraph 直接作为父节点；默认 per-invocation，不使用 `checkpointer=True` 同一子图并发 |
| Deep Agent engine spine | scripted `use_skill -> execute_ability -> render_application -> Finalizer` | 实际绑定 3 个 Runtime-owned Tool；真实 Skill Registry/Skill bytes、synthetic Ability port、DISPLAY_ONLY Application 各调用 1 次 | server artifact 不进 Tool content；Ability retry=0；未调用必需 Tool 的同步/异步 final response 均被 Finalizer 拒绝 |
| PG bootstrap credential safety | libpq SCRAM verifier + NOLOGIN gate | 3/3 synthetic sentinel 负例 GREEN | DDL/log/error 无 plaintext sentinel；失败确认 role disabled，无法确认则 UNSAFE_UNKNOWN 并要求销毁隔离 PG；尚未现场 PG 重跑 |

上述 scripted 用例没有证明模型必然调用 use_skill；system prompt 不是授权机制。Anthropic MockTransport 证明的是实际 provider serializer 路径，但不是 live-model 行为。INTERACTIVE 尚未执行合法 Action resume。

## PostgreSQL 门禁

SDK 场景必须最终使用 AsyncPostgresSaver 和真实 PostgreSQL：

- 调用 setup/migration；
- 两个独立 Python 进程共享同一数据库；
- process A 写 checkpoint/interrupt 后退出；
- process B 查询并按合法 InteractionRef resume；
- 结合获准的每分支 compiled subgraph 候选，验证 A resume 后父 join；首窗口不扩 generic crash recovery、model replay、业务 kill/reconciliation。

InMemorySaver、MemorySaver、SQLite 或单进程 mock 不能作为通过证据。

## TDD 证据规则

- 每个行为先运行失败测试，并确认失败原因是目标行为缺失。
- import error、Python 版本错误、网络失败或 PostgreSQL 未启动不算 RED。
- 实现后运行同一测试通过，再运行完整实验 suite。
- 所有 fixture 必须标记 synthetic/scripted；不能把 scripted model 结果宣传为 live-model 能力。

## 未验证门禁

- Deep Agents 默认 middleware/Tool 暴露已审计并收口；Tool exception 与 A2UI-only retry 行为尚未完成。
- scripted model 被预编程调用 use_skill，不能证明 live model 无法绕过；原始 args 闭合准入仅证明 probe 路径，不替代产品 Runtime guard。
- 平铺父图的 LangGraph 1.2.11 反例仍为 RED（只到 B1）；每个 Workflow 分支一个 compiled subgraph 的结构候选为 1/1 GREEN（A interrupt、B2 完成、join 未运行），但尚未完成 PostgreSQL/恢复验证，也不是已批准执行模型。
- PostgreSQL setup/persistence 与串行双进程恢复已在单一 synthetic graph 证明；同 thread 并发冲突、产品 migration、修复后 bootstrap 现场复跑与合法 Action resume 尚未证明。
- stop/restart、完整 Workflow accumulator 与真实 Ability 调用尚未证明；Finalizer 仅为 engine probe 的 required-successful-Tool 门禁。
- 真实模型、公共部署和业务系统均不在本次授权。
