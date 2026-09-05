# Agent/Workflow Runtime 回归计划

## 状态

- 回归状态：PLANNED
- 已执行场景：0
- Runtime 准出：NO READY
- 说明：方法名和字段是消费者需求草案，不代表共享协议已批准；所有结果均为期望值，不是实测证据。

## 计划场景

| ID | Method | Params | 期望成功 data / error | 字段级断言 |
| --- | --- | --- | --- | --- |
| R01 | RuntimeCommand.StartRun | runType=AGENT；assetRef/revision；中性 input；idempotencyKey；authContext | data={runId,state,revision,resolvedAsset} | state 为可运行态；resolvedAsset revision 与请求一致；重复同 key/同 fingerprint 返回相同 runId |
| R02 | RuntimeCommand.StartRun + Worker.AdvanceRun | runType=WORKFLOW；graphRef/revision；包含一个 Agent 节点 | data={runId,state,revision,childRuns} | Workflow 调度节点依赖；Agent 节点创建独立 childRunId；父运行不暴露子 Agent 内部消息 |
| R03 | RuntimeCommand.StartRun | 未发布或未知 asset revision / contractVersion | error={code,data:null} | code 为稳定的资产/版本拒绝类；不创建可运行 run；不尝试旧版本或其他协议 fallback |
| R04 | Worker.ClaimRunnable + Worker.CommitAttempt | 两个 worker 同时领取；首个租约过期；旧/新 fencingToken | data={runId,leaseOwner,fencingToken,state,revision} | 同一时刻仅一个有效 owner；接管 token 递增；旧 worker 晚写被拒；新 worker 从 PostgreSQL checkpoint 恢复 |
| R05 | CapabilityExecutionPort.Invoke | capabilityRef/revision；typedInput；固定 operationKey；注入“外部成功后进程退出” | data={typedOutput,effectReceipt,idempotencyStatus} | 恢复调用复用 operationKey；effectReceipt 稳定；外部副作用只发生一次；无幂等声明时不自动重试 |
| R06 | RuntimeCommand.SubmitAction | actionRequestId；expectedRunRevision；decision；authContext；重复/冲突 decision | data={runId,state,revision,acceptedDecision} | 首次合法决策原子生效；相同重复返回相同结果；不同决策或过期 revision 返回冲突；恢复不重复 interrupt 前副作用 |
| R07 | RuntimeCommand.CancelRun + Worker.CommitAttempt | cancel 与节点完成并发；expectedRevision；reasonCode | data={runId,state,revision,cancelAccepted} | 先提交的终态规则确定；取消后不启动新副作用；晚结果不推进主状态并产生审计事件；不声称已撤回既有副作用 |
| R08 | RuntimeQuery.SubscribeRunEvents | runId；afterSequence；authContext；包含 presentation/action event | data={events,nextSequence} | 只返回游标后的已提交事件；sequence 单调无复用；重复投递可按 runId+sequence 去重；payload 为通用 artifact/data/action 契约且无业务文案、renderer 或 raw chain-of-thought |

## 计划测试层次

- 契约测试：命令 fingerprint、error/data envelope、schema/version fail closed。
- PostgreSQL 集成测试：真实事务、unique constraint、租约时间、fencing 与 event sequence。
- 多进程故障注入：kill -9 worker、租约过期、网络超时、结果提交前崩溃。
- 端口假实现：记录 operationKey、调用次数和 effectReceipt，不使用业务 fixture。
- 传输适配测试：断线后按 afterSequence 回放，再切 live tail。
- 依赖检查：Runtime 包不得引用数字员工包、业务名词或 renderer 实现。

## 证据写入规则

执行后每个场景必须记录：commit、数据库版本、实例数、触发步骤、原始命令参数的脱敏摘要、成功 data 或 error、字段级断言和日志/trace 位置。只跑单测不能宣称多实例恢复或 Runtime READY。
