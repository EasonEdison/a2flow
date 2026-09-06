# Phase 1 回归与验证记录

## 总体状态

- 图 fixture 自检：`PASS (DOC_FIXTURE_ONLY)`
- Python 模块/依赖研究：`PASS (DOC_RESEARCH_ONLY)`
- `SW-P1-SUBSET-01` 权威同步：`PASS (DOC_AUTHORITY_ONLY)`
- 服务实现验证：`PLANNED`
- Runtime 集成：`NO READY`
- 说明：fixture 自检只证明项目自有 JSON 样例结构和声明的 case 编码一致；它没有施加 5 种 mutation，也没有运行 5 类 Runtime 行为，不证明共享 contract、LangGraph 行为或产品可用。

## R0 非规范图样例自检

- 状态：`EXECUTED (DOC_FIXTURE_ONLY)`
- Command：`python3 openspec/changes/oss-workflow-composer/examples/validate_phase1_examples.py`
- Environment：服务器专属 worker worktree；Python 3.6.8 标准库；未安装依赖
- Expected output：`phase1-workflow-fixtures: PASS nodes=11 edges=12 staticCases=5 runtimeCases=5 contextCases=2`
- Actual output：`phase1-workflow-fixtures: PASS nodes=11 edges=12 staticCases=5 runtimeCases=5 contextCases=2`（2026-09-07）
- 断言：JSON 可解析；node/edge key 唯一；全图无环；START/FINALIZER/END 唯一；decision candidates 与 CONDITIONAL edges 一致；parallel split/JOIN branch 集合闭合；A→B→C 与 join 后已执行分支 context cases 编码完整；样例不携带 environment/userId/credential。static/runtime cases 仍只是待执行用例目录。

## R0b Python 模块/校验栈公开资料研究

- 状态：`EXECUTED (DOC_RESEARCH_ONLY)`
- Method：读取 Pydantic、jsonschema、NetworkX、Python graphlib、pytest、Hypothesis、Psycopg、Deep Agents 的官方文档/PyPI 元数据，形成 `inputs/python-module-validation-candidates.md`
- Params：2026-09-07 可见的最新发布元数据、Python 要求、许可证和公开 DAG API；未安装或 import 候选包
- Success `data`：推荐 `shared JSON Schema + strict Pydantic + NetworkX`；Python `3.11+` 仅为兼容候选；根 pins/lock、系统 Python 和 Runtime 组合仍待单一 owner 实测
- 字段级断言：没有新增 `services/workflow-registry/`、根 manifest/lock、系统包或进程；研究结果不能把 G1-G7 改为 READY

## R0c `SW-P1-SUBSET-01` 权威同步

- 状态：`EXECUTED (DOC_AUTHORITY_ONLY)`
- Method：在本任务 worker `fetch + merge origin/main`，完整读取 `implementation-release-01.md` 并执行 SHA256 校验
- Params：release commit `3a48d4b106db8f382c3c96bbc8992f328b81e259`；expected SHA256 `c14eb61371562bf512b393ab347c80d2c4e3be082e4a7e838dc13e2a0f9743a4`
- Actual `data`：SHA256 完全一致；exact `skillKey/use_skill` 闭包来自 corrected schema snapshot `a1cb44e88ce5bb603c62b4618804c78ae0d5585c`
- 字段级断言：wire revision 仍为 `SW-CONTRACTS-P1-CANDIDATE.1`；Workflow owner、graph/context/control/events、Runtime readiness 和部署均未批准；27 项实现任务保持未勾选

## R1 发布合法 sequence/condition/parallel 图

- 状态：`PLANNED`
- Method：`ValidateWorkflowDraft`，随后 `PublishWorkflowDraft`（逻辑方法名，传输协议待 shared revision）
- Params：包含 decision MERGE、parallel split/JOIN、FINALIZER 的 fixture；`expectedDraftRevision`；control `requestId`
- Success `data`：`valid=true`、空 ERROR issues、`workflowRef`、`graphRevision`、`artifactDigest`
- 字段级断言：发布图保留稳定 node/candidate/branch identity 和 exact `skillKey`；移除 layout；不做 `skill:` 前缀猜测；相同 control request 返回同一发布结果。

## R2 非法拓扑失败关闭

- 状态：`PLANNED`
- Method：`ValidateWorkflowDraft`
- Params：分别应用 cycle、unknown candidate target、missing join branch、nested parallel、unreachable node fixtures
- Expected error：`data.valid=false`；issues 分别含 `GRAPH_CYCLE`、`DECISION_TARGET_UNKNOWN`、`PARALLEL_BRANCH_MISMATCH`、`PARALLEL_NESTING_NOT_SUPPORTED`、`GRAPH_UNREACHABLE`
- 字段级断言：每个 issue 含 node/edge/region 定位并按获批顺序稳定输出；nodes/edges 输入重排不改变语义结果；不得生成发布 artifact。

## R3 AI 不确定进入同节点 A2UI 选择

- 状态：`PLANNED`
- Method：Runtime `AdvanceDecisionNode`，随后 node-bound `SubmitInteraction`
- Params：全部相关已执行祖先最终结果/状态、发布 candidate 集合、selectionApplicationRef；合法 interactionId/nodeKey/config versions/selectedCandidateKey
- Success `data`：首次为 `WAITING_INTERACTION` 和候选卡引用；提交后为所选 `routeKey` 与 node completion
- 字段级断言：Skills 无 routing 字段；选择仅命中配置候选；用户选择不回到 AI 重选；AI 技术异常返回 FAILED 而非选择卡。

## R4 A 等待时 B1、B2 独立推进

- 状态：`PLANNED`，Runtime 强制门禁
- Method：Runtime `StartWorkflow`，读取 persisted node/branch/join states
- Params：有效图 fixture；A decision 强制语义不确定；B1/B2 scripted success
- Success `data`：A=`WAITING_INTERACTION`、B1=`SUCCESS`、B2=`SUCCESS`、JOIN=`WAITING`
- 字段级断言：B2 完成时间早于 A resume；JOIN 不把 A waiting 当 skip；LangGraph/Pg evidence 含稳定 run/node/branch identity。

## R5 allow-skip 与 required failure

- 状态：`PLANNED`
- Method：Runtime `AdvanceWorkflow`
- Params：先让 B2(ALLOW_SKIP) scripted failure，再让 A 路径 REQUIRED Skill scripted failure
- Success `data`：第一种 B branch joinEligible=true 且 status=FAILED；第二种 JOIN=BLOCKED 且 requiredFailureRef 指向 A 节点
- 字段级断言：容忍失败不改 SUCCESS；实际 skip 与 failure 分开；兄弟已完成结果不回滚；waiting 不自动 skip。

## R6 environment/userId 与版本失配 reset

- 状态：`PLANNED`
- Method：shared `ResolveEffectiveAssets`，随后 Runtime `SubmitInteraction`
- Params：trusted PRT/ONLINE context、userId、run 记录 versions、变更后的 effective versions
- Success `data`：PRT 只命中 PRT current；ONLINE 只命中 ONLINE stable/gray；失配返回 `resetRequired=true`
- 字段级断言：无 ONLINE→PRT 读取；模型不能覆盖 environment/userId；失配在新业务调用前阻断；不自动 restart。

## R7 A2UI-only retry、Finalizer 与 stop

- 状态：`PLANNED`
- Method：Runtime `RetryNode`、`StopWorkflow`、`FinalizeWorkflow`
- Params：A2UI Action configured-success failure；普通 Skill failure；accepted stop；合法 control request ids
- Success `data`：A2UI failure 可重入 owning node；普通 Skill failure retry denied；stop 后 Finalizer denied
- 字段级断言：已完成前驱/独立分支不重跑；业务重复调用由 API backend 处理；stop 后无新 node/model/Tool/Action/retry/Finalizer。

## R8 传递祖先 context 与 join 汇总

- 状态：`PLANNED`，Runtime 强制门禁
- Method：Runtime `BuildNodeContext`（逻辑方法名，具体 API 待 shared revision）
- Params：先执行 A→B→C，再执行选择 `a_fast`、不激活 `a_review` 且 B 分支完成的 parallel/join fixture
- Success `data`：C 的 ancestor entries 包含 A、B；Finalizer entries 包含真实执行的 A/B 分支祖先和 JOIN；`a_review` entry 不存在
- 字段级断言：每个 entry 保留 node identity、final result reference 和真实 status；不收窄到直接前驱，不为未选 candidate 生成占位结果；context 引用/预算不触发业务重执行。
