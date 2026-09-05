# Platform Contracts Specification

## ADDED Requirements

### Requirement: 稳定资产身份与不可变 Revision

系统 SHALL 使用稳定 `AssetKey` 标识逻辑资产，并 SHALL 为每次内容变化创建新的不可变 revision。展示名、slug 和可变 head SHALL NOT 成为跨域精确引用。

#### Scenario: 并发创建 Revision

- **触发**：两个调用方基于相同 `expectedHeadRevision` 同时提交不同内容。
- **期望结果**：至多一个调用成功推进 head；另一调用收到结构化前置条件失败，且任何已存在 revision 均未被覆盖。

### Requirement: 不可变 Release 冻结精确依赖

系统 SHALL 从一个精确 Revision 和零到多个精确依赖 Release 创建不可变 Release，并 SHALL 保存可重复验证的内容摘要。缺失依赖、可变引用或摘要不一致 SHALL fail closed。

#### Scenario: 发布含可变依赖

- **触发**：调用方以名称、latest 或环境 Pointer 代替精确依赖 Release 请求发布。
- **期望结果**：发布被拒绝，错误指出依赖引用不精确；系统不创建部分 Release，也不推进任何 Pointer。


### Requirement: 生效 Pointer 使用乐观并发控制

系统 SHALL 用带版本的 Activation Pointer 指向一个已存在 Release。更新 SHALL 要求当前版本前置条件，且 SHALL NOT 静默覆盖并发更新或自动回退。

#### Scenario: 过期 Pointer 更新

- **触发**：调用方使用已过期的 `expectedPointerVersion` 激活另一个 Release。
- **期望结果**：系统返回 412 或等价前置条件失败，并返回可重读的当前版本信息；现有 Pointer 保持不变。

### Requirement: Runtime 在 Run 内钉住精确 Release

Runtime 消费方 SHALL 在 Run 开始时解析一次 Activation Pointer，并 SHALL 持久化精确 `releaseId`、摘要和所见 Pointer 版本。运行和恢复 SHALL NOT 随后续 Pointer 更新漂移。

#### Scenario: 运行期间切换生效版本

- **触发**：Run 已钉住 Release A 后，有权主体把相同 Activation Pointer 更新为 Release B。
- **期望结果**：现有 Run 及其恢复继续使用 A；仅新 Run 可解析到 B，并能审计两次选择。

### Requirement: 授权上下文由可信边界构造

系统 SHALL 以 `issuer + subject` 标识主体，以 workspace 隔离资源，并 SHALL 在公共创建/读取/激活操作上默认拒绝。客户端 payload 中自报的角色或权限 SHALL NOT 被信任。

#### Scenario: 未授权主体尝试激活

- **触发**：已认证但缺少 `release.activate` 权限的主体请求更新 Pointer。
- **期望结果**：系统拒绝请求，不改变 Pointer、不泄露受保护 Release 内容，并写入脱敏审计结果。

### Requirement: 公共错误机器可判定

HTTP API SHALL 使用 RFC 9457 Problem Details 及稳定 `code`、`traceId`、`retryable` 扩展；客户端 SHALL NOT 依赖可本地化的 `detail` 做流程分支。

#### Scenario: 暂时不可用与业务校验失败

- **触发**：同一客户端分别遇到暂时基础设施故障和不可修复的 manifest 校验错误。
- **期望结果**：前者明确 `retryable=true` 并可携带 `Retry-After`；后者返回 422、稳定违规字段且 `retryable=false`。

### Requirement: 事件至少一次且可去重

生产者 SHALL 以 CloudEvents 1.0 信封在业务提交后发出公共事件。消费者 SHALL 按 `(source,id)` 持久去重，并 SHALL 只把同一聚合的 `aggregateversion` 解释为顺序。

#### Scenario: 重复且倒序交付

- **触发**：消费者收到重复的 `release.created`，随后先收到 aggregate version 5、后收到 version 4。
- **期望结果**：重复事件不产生第二次副作用；倒序事件不会回滚投影，缺口进入重取或可观测失败流程。

### Requirement: PostgreSQL 是唯一正确性真值

开发、测试和部署 SHALL 仅使用 PostgreSQL 保存公共契约状态。多实例 SHALL 通过持久唯一约束、事务和 CAS 保证正确性，SHALL NOT 使用 MySQL、SQLite 或内存 fallback。

#### Scenario: 两实例竞争同一幂等键

- **触发**：两个应用实例同时以同一幂等键和相同请求创建 Release。
- **期望结果**：两个调用观察到同一成功结果，数据库中只有一个 Release、一个幂等结果和不重复的领域事实。
