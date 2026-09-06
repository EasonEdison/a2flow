# 业务能力注册平台 Phase 1 回归计划

## 当前结论

- 基线：SW-P1-20260907.2
- 状态：`SW-P1-SUBSET-01` SOURCE SLICE PASS
- 源码验证：Capability Registry 19/19、Contracts Python 16/16、共享 schema 57/57、import smoke PASS。
- PostgreSQL/Runtime/部署/E2E 实际通过：0
- Runtime：NO READY
- 合成 fixture 静态检查：PASS；仅代表 fixture evidence，不升级 Runtime readiness。

## 已执行合成 fixture 证据

- 环境：服务器独立 worker worktree；现有 `Python 3.6.8`，未安装或升级任何依赖。
- 命令：`python3 -m json.tool services/capability-registry/fixtures/phase1/execute-ability.examples.json >/dev/null`。
- 命令：`python3 services/capability-registry/fixtures/phase1/validate_examples.py`。
- 输出：`PASS baseline=SW-P1-20260907.2 contract=SW-CONTRACTS-P1-CANDIDATE.1 cases=9 rejected_policies=2`。
- 输出：`PASS trusted_fields_hidden pre_call_failures_closed runtime_business_retries=0`。
- 输出：`PASS pointer_missing_closed found_null_distinct strict_json_types`。
- 限制：`runtime_evidence=false`；未运行 Registry、Runtime、PostgreSQL、adapter 或真实外部请求。

## 已执行 SW-P1-SUBSET-01 源码证据

- 环境：服务器独立 worker worktree；`/bin/python3.11` 为 Python 3.11.13；未安装或升级依赖。
- Contracts 稳定主干：`e7797830b09ac367db21f7dde51236e3189e77f3`；公开实现内容：`54a807bc061e79f77a7ba52bcf6d6827d6966481`。
- 命令：`python3 packages/contracts/tests/validate_contracts.py`；输出 `SUMMARY total=57 passed=57 failed=0`。
- 命令：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/contracts/src /bin/python3.11 -m unittest discover -s packages/contracts/tests/python -v`；输出 `Ran 16 tests`、`OK`。
- 命令：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/contracts/src:services/capability-registry/src /bin/python3.11 -m unittest discover -s services/capability-registry/tests -v`；输出 `Ran 19 tests`、`OK`。
- import smoke：`AbilityDefinitionValidator`、`AdapterOperationDescriptor`、`SharedResultPolicySetValidator` 均可导入。
- 源码边界：`git diff --check origin/main...HEAD`、owned-path scope、clean-room sensitive scan、无 HTTP/DB/process/evaluator/retry/idempotency/credential-value 行为、无 bytecode 和 `admin:admin` 属主检查均 PASS。

### AbilityDefinitionValidator.validate

- method：`AbilityDefinitionValidator.validate(payload)`。
- params：closed authored Ability mapping，包含 `abilityKey`、三份 schema、`inputBindings`、`credentialRequirements`、`adapterOperationRef`、`resultInterpretationPolicies` 与 `defaultSuccessPolicyRef`。
- success data：`AbilityDefinitionValidation(is_valid=True, issues=(), metadata=AbilityPublicationMetadata(...))`。
- 字段级断言：`ability_key=demo.catalog.lookup`、`adapter_operation_ref=demo.catalog.lookup.read`、`model_argument_paths=(/query,)`、`trusted_context_paths=(/userId,)`、`credential_slots=(demoRead,)`、`result_policy_refs=(okTrue,)`、`default_success_policy_ref=okTrue`，且 metadata 为 frozen dataclass。
- 失败断言：unknown/credential value/model server field/source/Pointer/target conflict/operation/input path/credential slot 均无 metadata；model source 不得写 `/userId`；`resolvedInputSchema.required` 缺少来源时报 `REQUIRED_INPUT_SOURCE_MISSING`。

### SharedResultPolicySetValidator.validate

- method：`SharedResultPolicySetValidator.validate(policy_set)`。
- params：`resultInterpretationPolicies[]` 与 `defaultSuccessPolicyRef` 的共享 mapping。
- success data：合法 policy set 返回 immutable empty tuple `()`。
- 字段级断言：duplicate policy ref 保留共享 `(path=$.resultInterpretationPolicies, code=duplicate_policy_ref)`；dangling default 保留 `(path=$.defaultSuccessPolicyRef, code=unresolved_default_policy)`；`path`、`code`、`message` 不改写。
- 限制：此 adapter 只调用 `ResultInterpretationPolicySet.from_mapping` 并映射异常 issue，不解释 output，不执行 policy。

### TDD 证据

- 初始 happy path 先得到 `ModuleNotFoundError: capability_registry`，再达到 1/1 GREEN。
- authored boundary 新断言先失败，adapter compatibility 三例先失败，随后分别达到 10/10、13/13 GREEN。
- 两个畸形 JSON 输入先触发 `TypeError`，修复后 15/15 GREEN。
- 主控审查的 model-to-userId 与 required-source-missing 两个最小变异先被错误接受，修复后领域测试 17/17 GREEN。
- shared adapter 先得到缺少 `SharedResultPolicySetValidator` 的 ImportError；稳定 Contracts 到达后修正 fail-fast 测试假设，最终全模块 19/19 GREEN。

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
| CA-09 | JSON Pointer 路径缺失 | output schema 仍合法；policyMatched=false；reasonCode=PATH_MISSING；不得当成 null |
| CA-10 | JSON Pointer 找到真实 JSON null，expectedLiteral=null | policyMatched=true；与 MISSING 结果不同 |
| CA-11 | observed string `"1"`、expected number `1` | policyMatched=false；不做隐式类型转换 |
| CA-12 | 发布 NOT_EQUALS 或 ALL/conditions AST | 静态拒绝 RESULT_POLICY_OPERATOR_UNSUPPORTED；不进入 Runtime 解释 |

## 计划接口证据

### execute_ability

- model params：`abilityKey`、`arguments`。
- trusted params：`userId`、`environment`、`authorizationContext`、observed versions、run/node context、`invocationId`。
- success data：`invocationId`、`abilityReleaseRef`、`status=SUCCEEDED`、`outputSchemaValidated=true`、`policyMatched=true`、`interpretation.matched=true`、`adapterCalled=true`。
- pre-call failure data：稳定 status/errorCode、`resetRequired`、`adapterCalled=false`。
- adapter failure data：`adapterCalled=true`、失败分类；无平台业务 retry/effect 推断。

## 未来验证层级

1. JSON/contract fixture：语法、字段分区和负向不变量。
2. Registry 单元测试：本批准子集已完成 19/19；完整 schema/output-policy 验证仍待后续。
3. PostgreSQL 集成：PRT/ONLINE 分库、revision、发布竞争。
4. Runtime contract：ToolRuntime 隐藏字段、resolver、授权、一次调用和唯一解释器。
5. A2UI integration：Action 对当前已解析且通过 version guard 的精确 release 选择 successPolicyRef；Action call 与 interaction completion 分离。

## 本批证据限制

- OpenSpec CLI 与项目依赖未安装时，不进行重型安装。
- 合成 fixture 与源码单测不调用真实 endpoint，不证明授权系统、数据库或 Runtime 已实现；`SW-P1-SUBSET-01` 是受限实现放行，不是完整 wire contract 或 Runtime readiness。
- 运行命令、环境、commit 和输出必须在实际执行后回填。
