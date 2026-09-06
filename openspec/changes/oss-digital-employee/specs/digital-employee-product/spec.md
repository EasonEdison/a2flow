# Digital Employee Product Capability Specification

## 状态

- Capability：数字员工产品与可复用 A2UI Web Host
- 设计：`PROPOSED`
- Runtime：`NO READY`

## ADDED Requirements

### Requirement: 运行必须由侧栏显式启动

数字员工产品 MUST 只通过侧栏 Workflow 启动入口创建 run，MUST NOT 把普通聊天消息解释为启动命令。产品 BFF MUST 从可信服务端上下文取得 `userId` 与环境，并以不可变 Workflow 发布引用和请求去重语义调用共享 Runtime；客户端 MUST NOT 覆盖主体或环境。PRT 与 ONLINE MUST 使用独立数据库与发布解析，PRT 只解析当前版本，ONLINE 才解析稳定/候选灰度。

#### Scenario: 用户显式启动合成 Workflow

- **WHEN** 已授权用户在侧栏选择 Workflow 与 PRT 后提交启动，而聊天区同时存在普通消息
- **THEN** BFF 只为侧栏请求创建一个 run，并返回权威 run 身份与起始 revision
- **AND** 普通聊天不启动 run，重复启动请求不创建第二个 run，客户端伪造的主体或环境被拒绝

### Requirement: 产品必须消费唯一的权威投影

产品 BFF MUST 通过共享合约读取 snapshot 和连续 run events，MUST NOT 自建第二套 event/action schema 或复制 Runtime 状态机。投影 MUST 按单 run sequence 排序去重；公共事件外壳的稳定身份只用于外壳去重。缺口或非法 delta MUST 阻断增量并补权威 snapshot。产品状态 MUST 使用 PostgreSQL，不得依赖 sticky session、MySQL、SQLite 或进程内持久化。

#### Scenario: 切换实例后出现事件缺口

- **WHEN** 同一 run 的消费从一个 BFF 实例切换到另一个实例，并收到重复、倒序和不连续事件
- **THEN** 新实例从 PostgreSQL 关联和 Runtime snapshot 重建投影，仅应用连续 sequence
- **AND** 缺口后的 delta 不被猜测或跳过，补齐 snapshot 后才继续

### Requirement: 用户输入必须绑定等待节点

等待用户输入的 Workflow 节点 MUST 在对应节点卡上开放结构化输入入口。BFF MUST 校验 run/node 关联、可信主体和所见 revision；普通聊天 MUST NOT 被解释为 continue 或 resume。

#### Scenario: 从错误入口提交相同文本

- **WHEN** 用户分别从目标节点卡和普通聊天提交相同文本
- **THEN** 只有节点卡请求被关联到等待节点并可能推进 run
- **AND** 普通聊天、错误节点、过期 revision 或错误主体不会改变 run

### Requirement: A2UI 显示与交互必须由配置区分

A2UI 配置 MUST 明确声明 DISPLAY_ONLY 或 INTERACTIVE。DISPLAY_ONLY surface MUST NOT 暂停 Workflow；INTERACTIVE surface 只在等待结构化 Action 时暂停。Action 的业务成功事实与“完成本次交互” MUST 是独立结果，Finalizer MUST NOT 覆盖 Tool 或 Action 的权威事实。Host MUST 只渲染获批 profile/catalog 的本地组件，未知版本或资产 MUST fail closed，且不得执行下发的 JavaScript 或任意 HTML。

#### Scenario: 先展示再交互

- **WHEN** 同一 run 先收到 DISPLAY_ONLY surface，后收到 INTERACTIVE surface 并提交 Action
- **THEN** 首个 surface 展示后 Workflow 继续，第二个 surface 等待 BFF 重新授权的结构化 Action
- **AND** UI 分别呈现业务成功与交互完成事实，未知资产只产生安全错误卡

### Requirement: 配置版本失配必须阻断并提示 fresh reset

start、continue 和 Action 在开始新工作前 MUST 校验轻量配置有效版本。版本失配 MUST 返回类型化错误并提示用户显式 reset，MUST NOT 继续冻结旧版本、静默迁移或自动重启。reset MUST 创建全新 run，不继承旧 context、checkpoint、results 或 interactions，也不得检查旧业务结果。

#### Scenario: continue 前配置版本已变化

- **WHEN** run 等待输入期间有效配置版本变化，用户提交 continue 后再显式 reset
- **THEN** continue 被阻断并返回 reset 提示
- **AND** reset 返回新的 run 身份，旧 run 的上下文和结果不进入新 run

### Requirement: stop 后所有分支与历史交互必须关闭

stop MUST 阻止 run 的所有分支开始新工作。迟到结果只可追加为事实，MUST NOT 触发后续节点。stopped run MUST NOT resume；其历史卡 MUST 只读，所有 Action、输入、retry 和 continue 操作都必须由后端类型化拒绝。

#### Scenario: stop 后收到迟到结果并操作历史卡

- **WHEN** 多分支 run 被 stop，随后一个已在途 Tool 返回结果且用户点击旧卡 Action
- **THEN** 结果只作为历史事实展示，不启动任何新工作
- **AND** 旧卡操作被拒绝，UI 保持 stopped 与只读

### Requirement: retry 与业务幂等必须遵守责任边界

只有 A2UI 渲染失败，或 Action 失败/结果不满足配置成功条件时，产品才可请求 retry 该 A2UI 所属节点。Skill、模型、非 A2UI Tool 与普通 Workflow 失败 MUST NOT 获得通用 retry。所有能力调用 MUST 通过 Runtime 的 `use_skill` 或获批 Tool；真实业务调用的重试与幂等只属于被调 API 后端，产品和 Runtime MUST NOT 查询旧业务结果、补偿或跨 run 去重。

#### Scenario: 四类失败同时出现

- **WHEN** 分别发生 A2UI 渲染失败、Action 失败、Skill 失败和业务 API 暂时失败
- **THEN** 只有前两类在满足配置条件时可 retry 对应 A2UI 节点
- **AND** Skill 失败不重试，业务 API 的策略与权威结果完全由被调后端决定

### Requirement: 可选长期记忆控制不得扩张成知识库

经仓库依赖、namespace、删除权限和最小 diff 核验，并由 main-brain 判定为 A/B/B+ 低成本后，产品 MAY 提供分页查看、逐条删除和禁用长期记忆；为此 MAY 增加最小偏好元数据与薄 facade，但 MUST NOT 改造记忆正文 schema 或索引。禁用 MUST 停止长期记忆读取与新写入，但 MUST NOT 终止当前聊天、当前 run 或短期上下文；删除记忆 MUST NOT 删除聊天。能力 MUST 限定当前可信 `userId`，不得扩张到上传、切块、共享、搜索调优或知识库管理。

#### Scenario: 禁用长期记忆后继续当前聊天

- **WHEN** 用户删除一条自己的长期记忆并关闭长期记忆开关
- **THEN** 后续长期读取与新写入停止，其他用户 namespace 不可见
- **AND** 当前聊天与当前 run 继续，聊天记录不因记忆删除而消失
