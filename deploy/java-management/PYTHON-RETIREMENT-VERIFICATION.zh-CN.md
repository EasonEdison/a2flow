# M Python 退役验证（2026-10-06）

## 源码

- 实现已合入主分支 `0c55d052a01593aaccacfb3b3398eaac5b97ceb7`，server origin/main 与 GitHub/main 一致。
- 删除旧 Python 管理 API/CRUD、Workflow composer 管理模块、发布桥接进程与旧部署入口；运行态公共校验与读取保留。旧 React 管理页面源码不是本次 Python 退役范围，未删除。
- Java 直接 JDBC 发布 Skill/Ability/Application；Python 独立 accounts 保留既有密码、会话和 M Cookie；未迁移账号数据。

## 验证证据

- 根合并验证：49 项保留模块与账号测试通过；8 个 Python Host/Runtime 模块导入成功，无法导入旧 a2flow_management。
- 根 JDK17 Maven test-compile、运行依赖打包及 PublicationMaterialTest 通过。
- 隔离数据库验证：Java 发布三类资产、幂等回执、碰撞、过期 CAS、依赖失败回滚、PRT/ONLINE 隔离通过。Python PostgresAssetRepository/AssetReader 实际读回 JDBC 材料成功。
- 4,996 个浮点数及 Unicode/控制字符样例跨语言规范化对照通过。另经独立源码审查未发现部署阻塞。
- 新账号临时实例 `/login` 返回200，旧管理路由404；临时实例验证后已停止。

## 实际部署

- 从干净 main 对应源码构建 Java，已部署；账号镜像 `a2flow-accounts:0c55d052` 已启动。未重建 B/业务执行容器。
- Java 使用部署后的真实凭据/Socket 对 PRT 和 ONLINE 分别完成数据库身份与 serving 摘要只读核对。
- 旧 Python M 容器及 publication 容器均 exited；Java M、Python accounts、原 B 均 running/restart0。
- 公网 `/login` 返回200；没有改 Nginx、账号/资产/历史数据库或删除卷。旧容器和镜像保留，可恢复。

## 未完成的人工会话验收

管理端浏览器会话在切换前已经过期，B 刷新后也要求登录。已请求用户正常登录；尚未完成这次部署后的已登录资产页面、真实新发布及历史卡片交互验收。隔离发布通过不等于公网发布已验收。

## 回退

私有部署目录保留切换前容器配置。恢复旧 Java release、停止新 accounts 后启动旧 Python M 8780，再启动旧 publication；不回滚或清空数据。禁止整栈 `down -v` 或 `--remove-orphans` 误停现有 B/数据库。
