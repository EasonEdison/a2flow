# Java 管理端部署

本目录负责已发布主分支的部署装配，不运行模型、不自动迁移旧资产、不创建测试账号。

## 数据与认证边界

- Java 管理表使用全新独立数据库；不能在已有 Python Runtime 数据库运行 V001，二者有同名表。
- 账号、密码和会话保留在既有数据库。Java 的独立账号连接只授予 users/sessions SELECT，数据库事务默认只读；不复制账号，不生成第二套会话。
- 登录代理调用独立 Python accounts 服务（loopback 8780）；它只负责账号会话，不提供旧 Python 资产管理 API。B/Agent/Workflow 运行态继续使用 Python。
- Java 直接向 PRT/ONLINE 对应 PostgreSQL 写入 Runtime 发布材料，不再启动 Python publication-bridge；配置使用 `A2FLOW_PUBLICATION_{PRT,ONLINE}_{JDBC_URL,USER,PASSWORD,DATABASE,NAMESPACE}`。
- 现有 PostgreSQL 仅提供 unix socket。Java 使用公开 junixsocket JDBC SocketFactory 直接访问既有 socket 卷，不桥接 TCP、不修改 PostgreSQL 监听或鉴权。应用由 Docker Compose 管理，宿主 Nginx 保持既有边缘设施。
- Java RPC 使用内部引擎专用 CA 的 mTLS。新证书只服务本项目，不能信任公共客户端 CA。缺少下游 target 配置时明确拒绝执行，不回退 HTTP。

## 操作顺序

1. 核对干净部署 worktree 的 main 与 origin/main 相同，记录旧镜像、Nginx 配置，备份两环境数据库；不停止旧服务。
2. 从该 SHA 的源码构建 Java classes/依赖和两个前端产物，保存为不可变 release；构建 Python SHA 镜像。
3. 私有目录保存 java.env、accounts.env、bside.env、管理配置与 RPC 证书；不得写入 Git 或命令输出。Compose 文件中的路径变量由部署环境提供。已有部署只增量转换配置，不能重跑 `prepare.py` 创建或覆盖数据库。
4. 创建新的管理库和专用角色；已有账号库只新增专用只读角色的授权。显式执行新管理库 V001，Runtime 只新增发布回执表，不改现有资产。
5. 首次部署使用 `docker compose --env-file <private-compose-env> -f deploy/java-management/compose.yaml up -d`。升级只更新指定服务，不整栈重启。旧 M 容器占用 8780 时，先受控停止旧 M 再启动 accounts，失败恢复旧容器；不要停止 PostgreSQL。先验证内网 HTTP / mTLS、真实账号登录和未登录拒绝，再切 Nginx 的管理 API、页面及 B 路由。
6. 运行 `nginx -t` 后 reload；验证公网页面、静态资源、深链接、登录和权限。不通过则恢复已备份路由；旧容器和数据库保留。

Java 新管理库最初为空。原 Python 演示资产和历史会话不会被删除，但不能冒充新 Java 已发布配置；需要在新管理台重新配置并发布才能进入新的 RPC 工具链。未登记真实业务 gRPC target 时，不宣称业务执行已上线。

本目录不提供默认管理员密码、公开匿名编辑或备用鉴权通道。
