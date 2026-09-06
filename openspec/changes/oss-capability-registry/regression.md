# 业务能力注册平台 Phase 1 回归计划

## 当前结论

- 基线：SW-P1-20260907.2
- 状态：PLANNED
- 自动化/集成/Runtime/E2E 实际通过：0
- Runtime：NO READY
- 合成 fixture 静态检查：PASS；仅代表 fixture evidence，不升级 Runtime readiness。

## 已执行合成 fixture 证据

- 环境：服务器独立 worker worktree；现有 `Python 3.6.8`，未安装或升级任何依赖。
- 命令：`python3 -m json.tool services/capability-registry/fixtures/phase1/execute-ability.examples.json >/dev/null`。
- 命令：`python3 services/capability-registry/fixtures/phase1/validate_examples.py`。
- 输出：`PASS baseline=SW-P1-20260907.2 cases=6`。
- 输出：`PASS trusted_fields_hidden pre_call_failures_closed runtime_business_retries=0`。
- 限制：`runtime_evidence=false`；未运行 Registry、Runtime、PostgreSQL、adapter 或真实外部请求。

## 计划矩阵

| ID | 触发 | 计划断言 |
| --- | --- | --- |
| CA-01 | 模型参数包含 userId/environment/credential/version | Tool schema/参数校验拒绝；adapterCalled=false |
| CA-02 | PRT 调用且 PRT current 存在 | 只访问 PRT 数据源；releaseRef=PRT current；ONLINE 读取数=0 |
| CA-03 | ONLINE 灰度 userId 命中 candidate | 只访问 ONLINE 数据源；releaseRef=ONLINE candidate；PRT 读取数=0 |
| CA-04 | observed 配置版本与 effective 版本不一致 | status=CONFIG_VERSION_MISMATCH；resetRequired=true；adapterCalled=false |
| CA-05 | 主体无 ability/operation/credential slot 权限 | status=AUTHORIZATION_DENIED；adapterCalled=false；不泄露其他主体/凭证 |
| CA-06 | modelArguments 或 resolved input 不符合 schema | status=ARGUMENT_INVALID；adapterCalled=false；错误含稳定 path/code |
| CA-07 | output schema 通过但 JSON_POINTER_EQUALS 未命中 | status=BUSINESS_NOT_SUCCESSFUL；interpretation.matched=false；不改写为成功 |
| CA-08 | adapter 超时或业务失败 | 一次 Tool call 的 adapter 调用数=1；Runtime 自动重试数=0；业务幂等不由平台宣称 |

## 计划接口证据

### execute_ability

- model params：`abilityKey`、`arguments`。
- trusted params：`userId`、`environment`、`authorizationContext`、observed versions、run/node context、`invocationId`。
- success data：`invocationId`、`abilityReleaseRef`、`status=SUCCEEDED`、`output`、`interpretation.matched=true`、`adapterCalled=true`。
- pre-call failure data：稳定 status/errorCode、`resetRequired`、`adapterCalled=false`。
- adapter failure data：`adapterCalled=true`、失败分类；无平台业务 retry/effect 推断。

## 未来验证层级

1. JSON/contract fixture：语法、字段分区和负向不变量。
2. Registry 单元测试：schema/binding/success policy 静态验证。
3. PostgreSQL 集成：PRT/ONLINE 分库、revision、发布竞争。
4. Runtime contract：ToolRuntime 隐藏字段、resolver、授权、一次调用和唯一解释器。
5. A2UI integration：Action 选择 successPolicyRef；configured success 与 completion 分离。

## 本批证据限制

- OpenSpec CLI 与项目依赖未安装时，不进行重型安装。
- 合成 fixture 不调用真实 endpoint、不证明授权系统、数据库或 Runtime 已实现。
- 运行命令、环境、commit 和输出必须在实际执行后回填。
