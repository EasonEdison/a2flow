# Python 管理能力退役

## 已确认边界

- Java 独占资产管理、编排、编译、发布与发布指针治理。
- Python 保留账号登录、B 端、Deep Agents/Workflow 和确定性业务运行态。
- 共享 Skill 读取和运行态所需资产校验不是管理接口，不随 CRUD 删除。
- 不删除账号、会话、资产版本、运行记录或数据库；不改变 PRT/ONLINE 隔离和现有发布语义。

## 改造

1. 将 publication-bridge 的 Skill/Ability/Application 数据库发布实现迁入 Java。直接连接两环境 PostgreSQL，维持不可变材料格式、摘要、事务、回执幂等与管理侧并发保护；不执行 Python 子进程。
2. 移除旧 Python 管理 API、资产草稿/编排 CRUD、旧入口及失效的专用测试。将混在管理模块内的运行态校验分离，验证 Python Runtime 导入不依赖已删除模块。
3. 登录从旧管理 Host 拆出为独立 Python accounts 服务，继续复用已有 users/sessions、密码算法、Cookie、角色、Origin 和限流策略。Java 登录代理继续调用 loopback 8780；账号服务不提供资产管理路由。
4. Compose 移除 publication 服务，增加 accounts 服务；Java 私有配置直接提供两环境发布 JDBC 参数，不再使用桥接 URL/token。

## 上线与回退

- 合入并验证主分支后构建。低内存服务器不执行 Maven/前端构建。
- 保存实际旧镜像、release 与配置；保留现有账号和发布数据库。
- 切换 Java 与 accounts 前核对 8780 占用。仅在新服务就绪后退役旧 Python M 和 publication 容器；数据库、B、执行服务不随整栈 down。
- 验证登录/会话、未授权拒绝、管理草稿和 Skill/Ability/Application 发布读回、Runtime 读取；仅使用受控验收资产，不重放用户已成功的业务 Action。
- 出错恢复精确旧 release/容器，不回滚或清空数据库。

## 验收状态

实施中。代码、部署、数据库发布和公网验收分别记录，本文不是已完成证明。
