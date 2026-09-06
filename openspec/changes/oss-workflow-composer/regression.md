# Phase 1 回归与验证记录

## 总体状态

- 图 fixture 自检：`PASS (DOC_FIXTURE_ONLY)`
- 服务实现验证：`PLANNED`
- Runtime 集成：`NO READY`
- 说明：fixture 自检只证明项目自有 JSON 样例结构一致，不证明共享 contract、LangGraph 行为或产品可用。

## R0 非规范图样例自检

- 状态：`EXECUTED (DOC_FIXTURE_ONLY)`
- Command：`python3 openspec/changes/oss-workflow-composer/examples/validate_phase1_examples.py`
- Environment：服务器专属 worker worktree；Python 3.6.8 标准库；未安装依赖
- Expected output：`phase1-workflow-fixtures: PASS nodes=11 edges=12 staticCases=5 runtimeCases=5`
- Actual output：`phase1-workflow-fixtures: PASS nodes=11 edges=12 staticCases=5 runtimeCases=5`（2026-09-07）
- 断言：JSON 可解析；node/edge key 唯一；全图无环；START/FINALIZER/END 唯一；decision candidates 与 CONDITIONAL edges 一致；parallel split/JOIN branch 集合闭合；样例不携带 environment/userId/credential。

## R1 发布合法 sequence/condition/parallel 图

- 状态：`PLANNED`
- Method：`ValidateWorkflowDraft`，随后 `PublishWorkflowDraft`（逻辑方法名，传输协议待 shared revision）
- Params：包含 decision MERGE、parallel split/JOIN、FINALIZER 的 fixture；`expectedDraftRevision`；control `requestId`
- Success `data`：`valid=true`、空 ERROR issues、`workflowRef`、`graphRevision`、`artifactDigest`
- 字段级断言：发布图保留稳定 node/candidate/branch identity；移除 layout；相同 control request 返回同一发布结果。

## R2 非法拓扑失败关闭

- 状态：`PLANNED`
- Method：`ValidateWorkflowDraft`
- Params：分别应用 cycle、unknown candidate target、missing join branch、nested parallel、unreachable node fixtures
- Expected error：`data.valid=false`；issues 分别含 `GRAPH_CYCLE`、`DECISION_TARGET_UNKNOWN`、`PARALLEL_BRANCH_MISMATCH`、`PARALLEL_NESTING_NOT_SUPPORTED`、`GRAPH_UNREACHABLE`
- 字段级断言：每个 issue 含 node/edge/region 定位；不得生成发布 artifact。

## R3 AI 不确定进入同节点 A2UI 选择

- 状态：`PLANNED`
- Method：Runtime `AdvanceDecisionNode`，随后 node-bound `SubmitInteraction`
- Params：前驱最终结果/状态、发布 candidate 集合、selectionApplicationRef；合法 interactionId/nodeKey/config versions/selectedCandidateKey
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
