# Python 内容业务服务运行说明

这是独立内容服务，不是 Agent 引擎，不会调用模型、抓取文章或发布到第三方。RPC 方法的业务参数中没有 userId；可信调用方通过共用 ExecutionContext 注入身份。

## 安装与配置

在隔离 Python 3.11+ 环境从仓库安装 `packages/rpc-contracts` 和 `services/content-service[rpc]`。数据只使用 PostgreSQL；PRT 与 ONLINE 用独立数据库和固定服务配置，不能让业务请求选择连接串。

| 配置 | 含义 |
| --- | --- |
| A2FLOW_CONTENT_DSN_FILE | 仅服务账号可读的连接配置文件；不在命令行、日志或 RPC 中传密码 |
| A2FLOW_CONTENT_DATABASE | 预期数据库名，每次连接核对实际数据库 |
| A2FLOW_CONTENT_ENVIRONMENT | 固定 PRT 或 ONLINE，其他环境请求拒绝 |
| A2FLOW_CONTENT_BIND | 显式 IP:端口，不自动开放公网 |
| A2FLOW_CONTENT_RPC_MODE | 生产 MTLS；只有隔离测试可显式 LOOPBACK_TEST，且只能监听 loopback |
| A2FLOW_CONTENT_KEY_FILE / CERT_FILE / CLIENT_CA_FILE | MTLS 私钥、服务证书、专用于可信执行服务的客户端 CA |

首次建表由有对应权限的操作者单独执行 `python -m a2flow_content --migrate-only`。启动服务用 `python -m a2flow_content`，不能靠启动服务自动修改表结构。

服务端强制验证客户端证书，缺少证书不降级；不接受浏览器直接调用。普通用户账号身份由现有产品鉴权获得，RPC 不转发 Cookie。首版最多四个并发 RPC，单请求上限 1MiB，响应上限 5MiB，不自动重试；deadline/断连不能证明业务没有执行。

## 独立联调

只针对新建隔离数据库和临时 loopback 服务运行：

```sh
PYTHONPATH=packages/rpc-contracts/src python deploy/content_service/verify_rpc.py \
  --target 127.0.0.1:临时端口 --allow-isolated-writes
```

探针会写入独立测试项目，走完三个确认和导出，并核对同请求重放、改变载荷冲突、其他用户不可读、旧版本冲突、缺失身份、环境不匹配。不连接生产库，不调用模型，也不代替 M 配置、Chat 或浏览器验收。验证后停止临时服务并清理测试数据库；凭据和真实业务正文不能进入证据文件。

## 当前交付边界

本目录不是已部署 Compose 服务。部署配置、生产证书验证、M 资产录入与发布、执行层 Python 迁移、Chat/A2UI 和 Workflow 接入须分别完成验收。可运行服务不能被表述为完整创作产品已经上线。
