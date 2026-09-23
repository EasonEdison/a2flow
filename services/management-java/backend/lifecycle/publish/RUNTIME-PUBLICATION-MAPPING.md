# Java 管理端 → 现有 Python 资产发布映射

状态：已实现回环 HTTP 发布桥和强类型 Java 适配器。
独立 PostgreSQL 测试覆盖真实发布及 Python 读取；部署和浏览器验收另行判断。

## 现有消费端契约

Python 资产库使用 `AF-MVP-08-ASSETS-1`。
不可变资产文档包含 `kind`、`key`、`assetId`、`versionId`、`definition` 和 `dependencies`；
其摘要为 Python 规范化 JSON 的 SHA-256，规则为键排序、UTF-8、无空白、不允许 NaN。
摘要单独存储，在 bundle 中通过 `contentDigest` 暴露。

SKILL 定义仅包含 `entries` 和 `requiredToolNames`。
每个条目包含 `handleId`、`logicalPath`、`mediaType`、`byteSize`、`contentDigest` 和 `base64`。
校验后的首个条目必须是文本 `SKILL.md`。
Java ZIP 的根目录为 Skill code；转换时必须去掉这一层根目录，拒绝不安全或重复路径，并使用现有 Python 包校验器检查解压后的大小及条目。
仅保存 ZIP 不会形成该定义。

依赖是不可变的编写态身份引用 `{kind,key}`，不是永久版本锁定。
`AssetReader` 按当前环境及用户分组解析依赖并记录生效版本。
现有 Runtime 入口检查发现版本不一致时要求 reset。
发布时依赖证据必须与这一运行策略区分；本适配器不能自行引入旧版本继续执行或永久版本锁定。

`PostgresAssetRepository.publish_candidate` 会先校验整个待发布命名空间及选中的 Application/Ability/Component 依赖闭包，
再原子写入 `a2flow_asset_versions` 和 `a2flow_asset_serving`。
它要求显式目标及 `expectedServingDigest`。
其返回结果表示真实生效版本选择，不只是留存归档。不能通过删除 Application Action 策略来通过校验。

## 必需输入映射

| Java 发布输入 | Python 输入／不变量 |
| --- | --- |
| 不可变包字节及包摘要 | 校验后的 SKILL entries；包摘要仍作为 receipt 证据 |
| 冻结发布快照中的绑定 | 显式、类型明确的依赖身份，不能重新查询当前草稿代替 |
| 稳定 Skill code | SKILL key；`assetId` 必须跨版本保持稳定 |
| 发布／构建身份 | 唯一不可变 `versionId`；仅使用数字草稿版本不足以区分重复 PRT 构建 |
| PRT 部署 | `CURRENT`，无灰度用户；显式绑定 PRT 数据库 |
| ONLINE 稳定发布 | `STABLE`，显式绑定 ONLINE 数据库 |
| ONLINE 灰度操作 | `GRAY` 及显式十进制字符串用户 ID，不能与稳定发布混用 |
| 先前 serving 快照 | `expectedServingDigest`，原子检查，冲突时不能静默刷新 |
| 平台 requestId | 同事务保存持久化请求摘要和 receipt；相同标识对应不同输入时拒绝 |

当前 Java Skill 适配器继承 `GrayReleasePolicy.DISABLED`，因此现有支持范围为 PRT CURRENT 和 ONLINE STABLE；
本任务不能开启 Skill 灰度操作。
表格中的 GRAY 行描述更广泛的契约边界，不是给本适配器追加功能需求。

PRT 和 ONLINE 必须分别配置数据库名及连接，修改前检查 `current_database()` 和 `a2flow_asset_environment`。
发布调用不得初始化 schema，也不得默认切换到另一环境。

## 集成决策及剩余边界

1. Java 现在从发布上下文传递不可变 `SkillPublicationInput`，包括来源 ID／摘要、冻结快照和 requestId。旧的直接包发布入口拒绝绕过该控制面的调用。HTTP 适配器读取 serving CAS 令牌，并提交精确的不可变输入。
2. 发布桥新增单独迁移的持久化请求 receipt，与现有 Python 发布器处于同一个事务。匹配的重试会核对已存不可变内容，返回原 receipt，不修改 serving。
3. 既有 HTTP 发布入口要求已认证管理员会话；Skill 还要求 Python 管理工作区通过 clean-state 检查。Java 工作区不会自动成为该工作区，盲目转发不能建立兼容性。
4. 既有 Python 运维 CLI 导入完整 bundle，不提供单次 CAS 发布及幂等记录事务。调用 `apply` 不能替代所需事务语义。
5. Java capability/Application schema 及标识必须显式映射到已发布的 Python 资产。不支持的 Action 语义必须明确失败，不能删除。首条兼容的 PRT 链路不代表 ONLINE／灰度支持，也不代表四类资产发布全部验收通过。

实现通过 `publication-bridge/` 复用现有 Python 校验器及发布仓储，没有在 Java 重写这些校验器，也没有引入 Agent/Workflow 执行循环。
部署时必须显式安装现有项目包、配置两个目标及服务认证，并执行 receipt 迁移。
这些操作尚未在已部署服务上执行。
