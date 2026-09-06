# Phase 1 execute_ability 合成契约样例

状态：`PROVISIONAL_CONSUMER_EXAMPLE`

这些文件只表达 Capability Registry 对共享 contracts、Runtime 和 A2UI 的消费需求。它们不是共享 schema 定稿，不冻结协议版本，也不是 Registry/Runtime 运行证据。

## 覆盖范围

- 模型只看到 `abilityKey` 和 `arguments`。
- userId、PRT/ONLINE、授权、版本和 credential reference 位于可信上下文。
- PRT current 与 ONLINE gray 都使用同环境 release。
- 版本失配、授权拒绝和参数错误在 adapter 调用前关闭。
- ability release 使用候选 `resultInterpretationPolicies[]` 与 `defaultSuccessPolicyRef`；仍不冻结 shared schema。
- output schema validity、policy match、Action call 与 interaction completion 分开。
- JSON Pointer `MISSING` 与 `FOUND(null)` 分开；缺失永不 match，null 可严格比较。
- JSON primitive 比较不做字符串、数字、布尔值或 null 的隐式类型转换。
- adapter 超时不触发 Runtime 业务自动重试。

## 合成与安全边界

- 所有 ID、输入和 credential reference 都是项目自造的 fixture。
- 除官方 JSON Schema `$schema` 标识外，不包含业务/API endpoint、secret、token、真实用户或真实业务数据。
- 不进行网络调用、数据库写或外部副作用。
- 被调用 API 后端拥有业务幂等与业务重试；`invocationId` 仅用于平台关联。

## 验证

在仓库根目录执行：

```bash
python3 -m json.tool services/capability-registry/fixtures/phase1/execute-ability.examples.json >/dev/null
python3 services/capability-registry/fixtures/phase1/validate_examples.py
```

校验器只使用 Python 标准库，验证样例内部不变量；它不实现 Runtime 解释器，也不替代 approved shared contracts schema 校验。
