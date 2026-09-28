# Python 业务与 A2UI 执行部署

管理端保留 Java；业务能力执行、A2UI 解释与内容业务服务使用 Python。此目录不启动第二套 Agent 历史或记忆系统。

## 服务边界

- `execution` 在一个 gRPC server 注册 `CapabilityExecution` 与 `A2uiExecution`，维持引擎现有单 channel 协议。
- `content` 提供阅读到创作的内容 RPC，自主管理 PostgreSQL 内容数据。
- 两者只监听回环地址并要求双向 TLS。传递可信 `userId`，不向业务下游转发浏览器 Cookie。
- 执行器只读管理端发布记录；运行素材库存只用于将 actionCode 映射到稳定资产身份，不能用其旧版本覆盖当前发布选择。
- A2UI 服务本身没有进程内会话持久化依赖。B 端必须持久化完整 TrustedCard，后续 Act 用其 snapshot 重放，并重新校验发布身份。

## 部署顺序

1. 从干净、已集成的提交构建镜像。`SDK_IMAGE` 必须指向已审核 SDK 镜像；本机镜像 ID 先打本地标签再用于 Dockerfile FROM，不把 `sha256:...` 当远端仓库名。
2. 备份现有管理库和 PRT 素材库。审核 `prepare.py` 的精确目标后执行一次：只新增内容库、内容角色和只读执行角色，不改现有业务记录。
3. 配置私有 DSN 文件、固定环境的 RPC targets 和证书。秘密不进 Git；目录 0700、文件 0600。
4. 显式运行 `content -m a2flow_content --migrate-only`，确认 `CONTENT_SCHEMA_READY` 后再启动服务；服务正常启动不隐式迁移。
5. 验证带客户端证书的真实 RPC，以及无客户端证书的拒绝行为。监听就绪不等于业务链路验收。
6. 在现有 Java Compose 上组合 `management.override.yaml`，先仅更新管理端的内容 RPC 验证目标。
7. 通过 `deploy/reading_content` 的正式管理接口创建、校验、发布 PRT 资产。不得直接拼发布表或绕过门禁。
8. 资产发布后再更新 B 端 RPC 目标及静态构建，验证真实模型、卡片 Action、刷新恢复和下载。

两个 Compose 应各自使用保留的私有 env 文件；组合 Java Compose 时必须同时使用原文件和 override，并明确指定服务，不能默认重启整套无关服务。

更新使用 Python 执行器的 B 服务时，命令必须显式包含 Python override；仅使用 Java
Compose 会保留 standalone Java 目标 `127.0.0.1:8793`，不能用于该组合部署：

```bash
docker compose --env-file <management.env> \
  -f ../java-management/compose.yaml \
  -f ./management.override.yaml \
  -f <private-overrides...> \
  up -d --no-deps --force-recreate bside
```

重建后必须核对 B 容器内 `A2FLOW_ENGINE_RPC_TARGET=127.0.0.1:8794`，并用同一
mTLS 配置执行一次只读 `Describe`；端口监听本身不证明 B 已连接 Python 执行器。

## 回退与验收

保留旧镜像、Java 静态 release 及旧 B 端 RPC 目标。服务回退只切换部署，不撤销已完成的内容写入；不得自动清库或补偿业务事务。当前仅验收 PRT；ONLINE 需要独立内容库、配置和发布门禁证明。

公开页面验证至少覆盖：管理员真实发布、Chat `use_skill`、能力 RPC、A2UI 显示、用户确认、稿件保存与导出、未保存修改阻断旧稿下载。源码检查、容器就绪与公网产品可用分开记录。
