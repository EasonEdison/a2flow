# Python 已发布业务能力执行服务

该服务承接 M 管理平台发布的业务能力，读取真实发布聚合、编译参数契约，再通过注册的 gRPC descriptor 调用业务下游。M 仍使用 Java；此服务不编辑资产，不执行模型循环，不负责 A2UI 渲染或 Workflow 调度。

## 执行链路

`CapabilityExecution.Resolve/Execute → skill_asset_release_state → 编译器 → 参数映射 → gRPC 下游`

- 读取权威 M 发布表，而不是可能滞后的 Python 资产投影。`asset_key` 为 M 的稳定 `draftId`，与业务 `actionCode` 不混用。
- 一次解析在短只读 repeatable-read 事务中读取 root 和拆分 `RELEASE_RECORD`，校验记录摘要、资产身份、版本引用及快照。数据库事务结束后才发起业务 RPC。
- PRT 只读取当前 PRT BUILD，不回退 ONLINE，也不使用灰度。ONLINE 只读取 ONLINE VERSION，按既有百分比和 signed64 userId 白名单选择稳定或灰度版本。
- 当前 M 发布聚合在同一管理数据库中保存两种环境指针。本次不改变 M 的物理存储布局；不能因此声称环境物理分库迁移已经完成。
- 每次 Execute 重新读取发布状态，要求调用方携带非空、匹配的 `expected_source_id` 和 `expected_source_digest`。不匹配返回 `FAILED_PRECONDITION/SOURCE_VERSION_CHANGED`，不会调用下游；上层负责提示重置。
- PC/APP/COMMON 选择遵循现有 M 契约。模型参数、常量、可信系统变量分开映射；模型不能设置 userId、环境、目标地址、Cookie 或平台 context。
- Resolve 即校验注册 descriptor、精确平台 ExecutionContext 和 unary 方法，不把坏契约暴露给模型。Execute 同样校验，不靠 Resolve 的旧缓存授权。
- 业务响应保留原始 ProtoJSON 结构；输出 schema 不合规显式失败，不静默补默认值。业务重试、幂等由下游负责，本服务不自动重试副作用。

## 启动

Python 3.11+，先安装仓库 `packages/rpc-contracts`，再安装本包的 `[rpc]` extra。

运行 `python -m a2flow_capability`，显式提供以下配置：

| 环境变量 | 含义 |
| --- | --- |
| `A2FLOW_CAPABILITY_DSN_FILE` | PostgreSQL 连接串文件，部署时限制读取权限 |
| `A2FLOW_CAPABILITY_DATABASE` | 必须精确匹配 current_database |
| `A2FLOW_CAPABILITY_ENVIRONMENT` | PRT 或 ONLINE |
| `A2FLOW_CAPABILITY_TARGETS_FILE` | 下游 targetKey → 环境 → endpoint JSON 文件 |
| `A2FLOW_CAPABILITY_BIND` | 监听 IP:端口 |
| `A2FLOW_CAPABILITY_RPC_MODE` | MTLS；隔离测试才可 LOOPBACK_TEST |
| `A2FLOW_CAPABILITY_KEY_FILE` | 服务端私钥文件 |
| `A2FLOW_CAPABILITY_CERT_FILE` | 服务端证书文件 |
| `A2FLOW_CAPABILITY_CLIENT_CA_FILE` | 可信调用方 CA 文件 |

目标配置保持 M 执行服务已有形状：`targetKey` 下按 PRT/ONLINE 配置 `host`、`port`、`trustCertFile`、`clientCertFile`、`clientKeyFile`。仅隔离 loopback 测试可指定 `loopbackPlaintext: true`，非本机明文被拒绝。无 HTTP 或明文自动降级。

入站 mTLS 认证的是受信任内部服务。userId 是该服务传入的用户身份，不是凭据；调用方仍负责用户登录、Skill 绑定和操作权限。本服务不能直接作为浏览器或任意模型的公开执行入口。启动只做只读就绪检查，不建表、不迁移数据库。

## 验证与边界

2026-09-24：隔离 PostgreSQL 中写入符合 M 发布结构的合成资产，启动两个真实 Python RPC Host，验证：

- 拆分记录恢复 → Resolve → Execute → 内容服务创建项目 → 真实 PostgreSQL 写入；
- 最大 signed64 userId 精确传递、请求重放、其他用户不可读取；
- 发布切换拦截旧来源且未新增业务项目；
- PRT 不回退 ONLINE，ONLINE 稳定/灰度百分比和白名单；
- 篡改拆分记录摘要被拒绝。

探针在 `deploy/capability_service/verify_published_content.py`。必须设置 `A2FLOW_VERIFY_ISOLATED=1`，只允许 `_test` 结尾的隔离管理库，`--seed` 在空库建立最小同形表并写入合成发布记录。需要另行显式迁移隔离内容库并启动两个 Host。连接地址来自 `VERIFY_CAPABILITY_ADDRESS`、`VERIFY_CONTENT_ADDRESS`，只接受 `127.0.0.1:端口`，不修改生产实例。

这些验证不是 M 页面作者发布、真实模型、A2UI/Workflow 或公网部署验收。本次未切换现有生产执行入口，后续仍需 Python A2UI 解释迁移和内容场景的真实 M 资产联调。
