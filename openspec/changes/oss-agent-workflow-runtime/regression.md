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

历史 PG-P1-01 使用 AsyncPostgresSaver；AF-RUNTIME-03 的同步 Action/Continuation 链使用官方同步 PostgresSaver 和真实 PostgreSQL：

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

## AF-RUNTIME-02 实际源码切片证据 — 2026-09-08

基线：605720f；范围记录 AF-RUNTIME-02。测试命令见 services/agent-workflow-runtime/README.md。
新增 24/24 GREEN；既有 Runtime 31/31 GREEN。仅本机进程/MemorySaver 与显式测试端口，不代表 PG 持久化或多实例锁通过。

| Method | Params | 实际 data / error | 字段级断言 |
| --- | --- | --- | --- |
| ActionService.submit | 仅 runId/nodeId/interactionId/actionName/controlRequestId/inputs；owner 由 backend 注入 | EXECUTED 或明确 ActionRejected code | userId/environment/businessSuccess/completed/runtime 顶层注入拒绝；错误 owner、node、run、interaction、action 或 input 时 executor=0 |
| ActionService.submit | recorded/current Application/Ability/Skill 任一版本不匹配 | RESET_REQUIRED | executor=0，不执行旧配置、不自动 reset |
| ActionService.submit | actual result accepted=false；或 accepted=true 但 save_choice 不完成 | business_success 与 interaction_completed 独立 | 前者 false/false；后者 true/false；无 Command，原生 wait 仍在 |
| ActionService.submit + LangGraphContinuation | 合法 Action、配置允许完成 | true/true；resume_status=RETURNED | 按 snapshot 中匹配的 native interrupt ID 恢复，仅携带保存的 requestId 引用；原渲染 controlRequestId 保持 |
| ActionService.completion | 原始 Command 注入 businessSuccess/completed | 保持原生 interrupt | executor=0、无模型完成；停止/版本错误仍明确抛出 |
| DeepAgent.invoke / ainvoke | 模型在另一次同名 DISPLAY_ONLY Tool 成功后输出完成 | REQUIRED_INTERACTION_PENDING | 真实 Action 失败或成功但不完成均不能被同步/异步 Finalizer 推翻 |
| DeepAgent.invoke + Command | use_skill → INTERACTIVE → 合法完成 → Finalizer | 完成正例通过 | 原 Skill 调用 1 次、executor 1 次；resume_consumed=true；新 invocation 不借用旧工具证据 |
| 两个同 app/action Tool | 同模型步两张不同 interactionId 卡片 | 只完成指定卡 | 第一张完成后第二张 WAITING；两张实际完成后才允许 Finalizer |
| 控制去重 | 同 requestId/相同 payload；或同 ID/变更 payload | 原记录 / CONTROL_REQUEST_CONFLICT | 相同控制 executor 1 次；resume 异常后重复请求仍返回 UNCONFIRMED，绝不重复业务 |
| 运行中 stop/version change | executor 已返回真实成功 | RUN_STOPPED / RESET_REQUIRED | 保存真实结果，不 resume，不删除历史 |
| Native branch graph | A 交互等待、B1→B2、join | A 未完成时 B1/B2 已完成；A 合法完成后 JOIN | B1/B2 各 1 次、JOIN 最后；不假定跨分支 reducer trace 为串行顺序 |

开发中暴露并修复：持 admission lock 调用 graph 会阻塞 SDK 另一线程重放 Tool；
改为独立 continuation_scope 串行化图调用并在 Tool 处重新核验保存记录。最初的 trace
末尾串行顺序断言产生 RED，改为分支恰一次与 JOIN 最后断言。

## AF-RUNTIME-03 离线证据 — 2026-09-08

采用基线 87e17e7322f3932e0e84e2caa501a92bfcf10465。新 suite 输出：
Ran 47 tests ... OK (skipped=9)，即 38 个实际离线通过；9 个 PG 用例未运行。
实验 suite：Ran 37 tests ... OK。git diff --check 通过。
受控窗口脚本仅执行 --help，未创建容器/数据/密码文件。

- owner/environment 条件进入所有库读取；错误 owner 不再先读取他人记录，统一 INTERACTION_NOT_FOUND。
- 同一 scope 使用持锁连接，save 单独 transaction 提交；测试 executor 边界无活动 transaction。
- 断连接/释放锁/commit 不确定均拒绝；scope 不创建替代连接，退出 close。
- continuation session 丢失后不允许进入新的 admission scope 补写 RETURNED。
- schemaVersion 类型、闭合字段、canonical request、Attempt owner/key、结果 JSON 和完成跨字段引用校验通过。
- 主控独立复现的 COMPLETED + consumed + 无成功 Attempt 坏记录已拒绝；成功结果先存储、尚未 dispatch 的合法状态仍可往返。
- 同 request 历史读回不派发；在途/未确认 run 新请求拒绝且不污染历史；正常同 run 多卡串行完成可继续。

PG 计划（尚无运行态证据）：独立进程等待/完成读回、同请求一次 executor、不同卡不丢更新、
owner/env/stale/stopped executor=0、payload conflict/UNCONFIRMED 跨进程保留、杀本探针进程、
终止本探针持锁 backend、真实 Skill→交互→进程退出→Action→同步 native resume→Finalizer，
B1/B2 不重放。失连测试特意在真实图已完成 Tool、进入 finish_a 后切断 continuation session，
允许图继续 JOIN，但持久 DISPATCHING 不自动 RETURNED、不自动派发；这是限制验证而非恢复能力。

连接峰值将由 5ms pg_stat_activity 观测报告（含 observer/checkpointer/scopes/worker），
明确不是绝对瞬时峰值；role limit=8 为独立硬上限。

- AF-RUNTIME-03 窗口审查补充：显式禁用 LangSmith/LangChain tracing；独有 window marker + UID/group/session 验证后仅清理本脚本进程组；无论 parent 退出、killpg 竞态或双超时，finally 都执行日志检查和精确资源清理。模拟 PG-owned socket 权限失败已验证仅针对 PRIVATE/socket 的 sudo 删除，以及残留显式失败。docker logs 在清理前仅做本次两个 secret 的内存 substring 检查，只输出 PASS/FAIL。6 个离线故障测试通过，PG 仍未运行。

## AF-RUNTIME-03-PG-W1 实际证据 — 2026-09-08

- 单执行者窗口已获 main-brain 明确授权，仅运行一次，无重跑。
- 固定源码：660db6a7dffe0c6f270f3e0c84767aab36d87f70；运行期间 HEAD/hash/dirty 不变。
- 脚本 SHA256：103e9dcd2b36767bbf1483d84d57605928cc9ade2a5f6870080d284b2cdcfc1b。
- 命令：admin 在 worker 根执行 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=experiments/runtime-phase1
  /home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python -m runtime_phase1.runtime03_pg_window --authorized-window。
- PostgreSQL：17.11 (Debian 17.11-1.pgdg12+2)，固定已审 ECR digest。
- 实际输出：Ran 9 tests in 87.651s / OK；exit=0；总窗口 105.14 秒（含 pull）。

| 实際用例 | 断言结果 |
| --- | --- |
| 新独立进程读等待与完成 | WAITING/COMPLETED 持久读回；resume_consumed=true，executor 计数1 |
| 两进程同请求及 payload 冲突 | 两次返回 EXECUTED；数据库 executor 计数1；变更 payload CONTROL_REQUEST_CONFLICT |
| 两张卡并发更新 | 两卡历史各1；executor 计数2；没有覆盖另一张卡 |
| owner/env/版本/stop 负例 | 错误 owner、环境、Application/Ability/Skill 任一版本、stopped 均在 executor 前拒绝，计数0 |
| executor 未确认跨进程 | EXECUTION_UNCONFIRMED 保留；相同请求不重派发；另一张卡拒绝且不新增占位 |
| 精确杀本次 worker | 已提交 EXECUTING 保留；新进程投影 EXECUTION_UNCONFIRMED；executor 不重派发 |
| 精确终止 admission backend | 外部 executor 独立连接先看见已提交 EXECUTING；在途动作返回后 LOCK_CONNECTION_LOST；不换连接续写 |
| 同步 PostgresSaver 真实链路 | Skill→交互→进程退出→新进程 Action→指定 native interrupt resume→Finalizer/JOIN；Skill/B1/B2/A/executor 各1 |
| 在途图失锁限制 | completion Tool 后终止 continuation backend；真实图仍可继续 JOIN；持久 DISPATCHING 不改 RETURNED，重复请求不派发，新 Action gate 拒绝 |

以上 executor/Skill/B1/B2/A 计数均保存在 PostgreSQL，不是跨进程失效的内存计数。
图的 continuation 使用官方同步 PostgresSaver；测试没有替换为 AsyncPostgresSaver。
最后一项明确证明锁丢失不能撤回在途图，而非宣称恢复/全生命周期排他。

| 资源/安全观测 | 实际值 |
| --- | --- |
| 连接观测峰值 | 4；每5ms采样，包含 observer；不是绝对瞬时最大值，role硬上限8 |
| 最低可用主机内存 | 1039332 KiB |
| swap 最大增长 | 0 KiB |
| 数据高水位观测 | 49792 KiB |
| 清理前 Runtime sessions / advisory locks | 0 / 0 |
| 公开端口 | {}，network=none |
| 本轮明文 secret 日志检查 | PASS；只输出结论，未回显容器日志或 secret |
| 精确清理 | a2flow-runtime03-pg、a2flow-runtime03-pgdata、/home/admin/OpenSource/.tmp/af-runtime-03-pg 均删除 |
| 镜像 | 本次新拉镜像删除；原有无关 pause 镜像保留 |
| 独立复核 | 容器/volume筛选无结果，private dir不存在，5432无监听，源码660db6a/hash不变且clean |

临时 synthetic 数据与本次secret文件不可恢复地随隔离资源删除；不宣称 secure erase。
空 .tmp 父目录保留。该窗口已关闭，不构成再次运行或生产部署授权。
本次窗口失败安全检查套件为7个，实验 suite 当前38/38，普通Runtime38 PASS + 默认9 PG SKIP。

## AF-RUNTIME-04 离线固定版本前证据 — 2026-09-08

授权基线 a38444e8006ecef51a67f92a6b06a7d80285277b；
受影响源码及本段记录由同一 worker 提交固定，最终 SHA 见 Git 提交和主控回执。
所有命令在 admin-owned worker 根执行；显式关闭 tracing，没有配置 PG 凭据。

服务实际命令：

```sh
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=packages/contracts/src:services/agent-workflow-runtime/src:services/skill-registry/src:experiments/runtime-phase1:experiments/runtime-phase1/tests \
timeout 60 /home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python \
  -m unittest discover -s services/agent-workflow-runtime/tests -q
```

实际输出：Ran 69 tests in 3.228s / OK (skipped=9)，exit=0；
即 60 实际离线 PASS，9 个旧 AF03 PG 用例 SKIP。不得计为 69 PASS 或 AF04 PG PASS。

实验实际命令：

```sh
LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=packages/contracts/src:services/skill-registry/src:services/capability-registry/src:experiments/runtime-phase1:services/agent-workflow-runtime/src \
timeout 45 /home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python \
  -m unittest discover -s experiments/runtime-phase1/tests -q
```

实际输出：Ran 38 tests in 0.879s / OK，exit=0。

| AF04 已执行离线证据 | 实际断言/边界 |
| --- | --- |
| 无卡片 stop/owner/env/条件 success | STOPPED 持久测试记录；错误身份拒绝；七种后续 admission 与成功转换拒绝 |
| 在途 Action stop | executor 中已见 EXECUTING 与 Run IN_FLIGHT、Run fixture transaction 已退出；stop 不等待 admission 长锁；晚业务成功和 operation RETURNED 保留且不 resume |
| 真实主模型/summary | 主模型晚 response 存 RETURNED；强制 summary 首次普通 ValueError 后 stop，SDK retry 的实际 callback 阻止第二次 generate，actual call=1 |
| 并行 Tool/mixed-fatal | 两个已准入 Tool 结果均保存；无新模型；stop 先报错但晚 sibling KeyboardInterrupt/SystemExit/custom BaseException 仍向上传播 |
| 并行 Workflow MODEL node | parent 两节点各调用真实 Deep Agent；MODEL facts 分别 branch-left/branch-right，内容各匹配，非入口或 SDK model 名 |
| 节点/路由 | 节点实际结果保存后 stop；business router=0、successor=0 |
| 受控交互正链路 | Skill once→native wait→Action executor once→指定 native resume→Finalizer RETURNED→Run SUCCEEDED |
| AF04 组合 fail-closed | raw graph、legacy Action service、legacy continuation、raw continuation graph、不同 lifecycle 均拒绝；四种 continuation 错配 executor=0/无新 Attempt |
| 旧入口关闭/fresh | 旧 card/Command/continuation 拒绝；新 run/thread/interaction 不同；旧 full Run/versions/input/facts/Action/node/checkpoint 读取 spy 禁止 |
| canonical restart | 两个并发相同 control 只执行一次 factory/business；当前配置 v2/新输入/空旧状态；冲突输入拒绝；旧 UNCONFIRMED 不成为新门禁 |
| 原 fatal/启动不确定 | fact/control receipt 保存失败不替换原 KeyboardInterrupt；factory 失败后相同 control 不再次启动 |
| PostgreSQL窄投影/闭合记录 | mocked SQL 不 SELECT 旧 document/input/versions；损坏活动 Run 字段仍拒绝；不算真实 PG 存储验证 |

真实 SDK 指安装的 Deep Agents 0.7.13/LangGraph 1.2.11 同步运行，
模型和业务端口均 synthetic、存储为 MemorySaver 或显式离线协议 fixture。
测试修复过两类装配错误：4 个旧测试漏 RunGraphBinding；并行测试错误使用
单值状态/空状态，以及两个测试漏有效版本配置。最后输出已全绿，不保留此前失败为当前结果。

AF04 live PG 完全未运行，独立脚本尚未准备。待单独评审的最小 PG 证据：
独立连接同时看见 Run/Action 已提交准入后才 dispatch；Action 长 session 期间另一进程
接受 stop；跨进程旧 card/native resume 禁止；stop/admission/success 竞争；
真实同步 PostgresSaver fresh restart/new interaction 和同 control 竞争 invoke=1；
晚真实结果保存、资源/secret/finally 精确清理。现有 AF03 窗口授权不可复用。

## AF-RUNTIME-04-PG-W1 单次实际证据 — 2026-09-08

本节是 AF04 PostgreSQL 的最新证据；此前 NOT RUN/窗口待审段落保留为历史，
不得将本窗口解读为再次运行授权或产品 READY。

- 主控单独释放 W1；唯一 executor 为本任务，admin 在 owned worker 执行一次。
- 固定源码：998b4d9f8411a8e09b88abfb665adb330db15e9f。
- Runtime 实现仍为已审 6ee09e3；窗口修订来自 9632250，998b4d9 只追加 checkpoint。
- 命令：PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=experiments/runtime-phase1
  /home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python
  -m runtime_phase1.runtime04_pg_window --authorized-window
  --expected-source-sha 998b4d9f8411a8e09b88abfb665adb330db15e9f。
- 入场与清理后 HEAD/clean/四文件 SHA256 完全一致；窗口期间未改任何 tracked 文件，包括 checkpoint。
- 真实输出：Ran 8 tests in 111.491s / OK；exit=0；无 skip、无重跑。
- PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2)，已审 ECR linux/amd64 digest。
- 脚本清理前累计 elapsedSeconds=130.26（含 pull/准备/测试，不冒充整个 finally 完成耗时）。

| 已执行 PG 用例 | 固定源码中的实际断言通过 |
| --- | --- |
| 已准入原生 node 晚结果 | handler 在 PG event 屏障中等待；另一进程 stop 返回后旧 child 仍在运行；释放后 node fact RETURNED 含实际结果，Run STOPPED |
| fresh restart 并发控制 | 两 child 分别 ready 后 parent 释放；factory=1、同 runId、新 run/thread/card、current v2/新输入；旧成功 Action 与 UNCONFIRMED 均未抑制新 Action；旧新 executor 总计2，Skill总计2；冲突payload拒绝，旧历史digest不变 |
| 完成型长 Action stop | executor 第三连接看见 AF03 EXECUTING 和 AF04 IN_FLIGHT 都已提交；stop 不等长 Action session；晚 success+interactionCompleted=true/COMPLETED/RETURNED 保存；resumeConsumed=false、NOT_REQUESTED；native_resume/Finalizer/真实successor计数各0 |
| 无卡 stop/身份/去重 | 错owner/env均RUN_NOT_FOUND；无卡Run可stop；独立进程重复同control读回相同STOPPED快照 |
| 正链路跨进程同步 saver | Skill→native wait→进程退出→Action→native resume→Finalizer→真实successor→SUCCEEDED；Skill/executor/native_resume/Finalizer/successor各1 |
| stop vs conditional success | 两进程PG屏障竞争；只允许一个合法提交终态，败方拒绝；输出未记录本次哪方获胜，不宣称覆盖所有交错 |
| stop vs node admission | 屏障采样竞争；已有node fact只能revision0并保存RETURNED；STOPPED后新进程dispatch不增加；不宣称每种race分支均被本次采样覆盖 |
| 旧卡/native Command关闭 | 从独立进程提交旧完成型Action和raw native Command均STOPPED；executor=0，old checkpoint读取spy不触发，旧历史digest不变 |

fresh restart 进程对旧 full Run/input/versions/Action/node/facts/checkpoint 读取设置拒绝 spy，
且旧 input/versions 刻意损坏。只允许窄旧身份/status/definition投影；新图正常等待和完成。
上述 counters/barriers 全部存在本次隔离 PG 中，非进程内计数。
模型/业务仍是 synthetic；强制 summary、并行 model-node 归属、mixed-fatal 的较广覆盖
来自独立离线用例，不借本次8项扩大为任意 DAG/live provider/async/恢复验证。

| 资源与安全 | 实测值 |
| --- | --- |
| 连接观测峰值 | 5；5ms、含observer；不是绝对瞬时最大，role硬限8 |
| 最低 available | 1036340 KiB |
| 最大 swap 增长 | 0 KiB |
| 数据高水位采样 | 50112 KiB |
| 清理前 runtime sessions / advisory locks | 0 / 0 |
| 公开端口 | {}；network=none |
| 明文凭据日志检查 | PASS；没有回显容器日志或凭据 |
| finally精确清理 | a2flow-runtime04-pg / a2flow-runtime04-pgdata / /home/admin/OpenSource/.tmp/af-runtime-04-pg |
| 新拉镜像 | ownedImageRemoved=true；独立精确inspect也确认不存在 |
| 独立收尾读回 | container/volume exact筛选均空；private目录不存在且非symlink；5432无监听；HEAD仍998b4d9且clean |

独立收尾核验时间：2026-09-08 06:01:57 UTC（14:01:57 Asia/Shanghai）。
隔离 synthetic 数据及本轮凭据随精确资源清理移除，不可从这些已删资源恢复；
不宣称 secure erase。未删除 .tmp 父目录，未操作其他数据/服务。
W1 已关闭，不再运行 PG，不集成 main，不操作 GitHub；证据文档交主控验收。
