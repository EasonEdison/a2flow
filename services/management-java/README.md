# A2Flow Java 管理端与确定性执行服务

当前接入说明：[业务能力与 A2UI 的 Chat 执行链](RPC-CHAT.zh-CN.md)。已实现手填管理 HTTP 宿主、PostgreSQL/MyBatis 装配、环境资产发布桥和两段 gRPC。生产配置与部署单独验收，不连接原公司服务。

保留四类管理资产与分阶段编辑页面。前端独立使用 React/Ant Design/Vite；Java 只依赖公开 Maven 库，不依赖公司父 POM。审批、对象存储、公司 RPC 与配置适配器已移除或替换。暂停能力的地址占位使用 example.invalid，不构成可执行兜底。

Skill 文件保存在 PostgreSQL 草稿文档中，带修订校验和事务边界。构建产物使用专用命名空间下的不可变资产版本记录。产物保存不等于 Runtime 发布；恢复历史包必须校验数据库原文与摘要，不信任旧本地目录。

独立宿主提供 `/api/management/v2` 接口。M 端 AI 辅助生成暂停；Java 确定性执行不替代 Python Deep Agents 的模型循环。INTEGRATION-GAPS.md 是历史迁移基线，最新边界以 MANUAL-MODE.zh-CN.md 与 RPC-CHAT.zh-CN.md 为准。源码不包含原数据库、凭据或公司配置值。

## 构建

使用 Java 17 和公开 Maven Central，不使用公司私有镜像：

```sh
mvn clean compile
cd frontend
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run build
```

通过外部 JSON 文件 `A2FLOW_MANAGEMENT_CONFIG` 提供配置，`A2FLOW_ENVIRONMENT` 明确指定 PRT 或 ONLINE。禁止提交含凭据的配置；权限或必需配置不满足时拒绝启动／执行。

宿主与业务下游配置见 [RPC 配置](backend/capabilityrpc/README.zh-CN.md)。Java 当前固定监听 loopback，开启 mTLS 不会自动向其他机器开放监听。

隔离 PostgreSQL 上的真实管理 HTTP 编写与 PRT 发布检查已通过。最终 Chat 证据见 RPC-CHAT.zh-CN.md。真实账号服务装配、生产证书检查、公网页面完整验收及部署仍是独立门禁；本机合成业务联调不等于生产上线。
