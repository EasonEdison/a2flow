# M 端查询整改

日期：2026-10-13。范围仅 Java 管理查询，不改运行态、发布状态机或动态 A2UI。

## 已实现

### Skill 列表完整性

- 移除主列表“先取 100 条，再在 Java 中筛选分页”的路径。
- `SkillListQuery → SkillListRepository → SkillListMapper`：关键词、分类、专员和状态先在 PostgreSQL 过滤，再 `LIMIT/OFFSET`。
- 更新时间倒序，以 ID 倒序消除同时间记录的排序歧义；页面文案同步为更新时间。
- 返回 `SkillListItem` 摘要，不加载工作区文件或完整发布历史；详情保留原来的完整模型。
- `total` 包含当前所有筛选条件；编辑中/已上线计数保留原规则，不受状态选择本身影响。
- 单次请求的列表与计数使用短只读 REPEATABLE READ 事务。不同翻页请求间不承诺快照一致，期间更新的资产仍可能移位。
- 多专员关系不放大列表或 total；关联严格匹配 namespace、源类型、源 ID、源版本与关系类型。

### 能力列表关联查询

- 关键词改为参数化 SQL 字面量包含匹配，不先取全部 JSON 再匹配；保留大小写不敏感和 `%/_` 的字面量含义。
- 分类投影复用通用 relation Repository，每 100 个当前草稿按三类关系批量读取。
- 空分类是合法结果，不再作为“尚未读取”的标记触发重复查询。
- 125 个草稿的分类关系查询为 6 次，不代表整个能力列表接口仅有 6 次 SQL：发布状态等路径仍待整改。

### 当前环境发布快照（第三批）

- `PublishedAssetQueryService` 使用独立的 `PublishedReleaseStateRepository` 读模型；历史详情、发布、回滚继续使用原完整聚合 Repository，不把裁剪模型用于写入。
- 根行仍是读取时的环境指针快照；Build/Version 索引以 200 条为一批，仅返回类型化 `ReleaseRecordHeader`。PRT 按 Build ID + targetVersion，ONLINE 按原版本号和数组顺序选择；不回退其他环境或草稿。
- 正文仅加载所选记录，Version 的 `snapshotBuildId` 追加精确来源 Build；ONLINE 独立派生快照仍读 Version 自身内容。部署流水不参与当前快照读取。
- Build/Version 索引 SQL 检查不可变记录原始字符串的 SHA-256，Java 检查归属、集合、记录 ID 与引用缺失；被选中的正文继续复用原 `hydrate` 的完整摘要/引用检查。
- 此优化减少数据库返回的大字段与 JVM 历史快照展开量，**不是数据库完全不读历史**：数据库仍提取并校验历史索引，根行引用数量与历史增长相关。旧无格式标记的内联聚合保留原完整读路径，不隐式迁移。
- 当前读路径不再审计无关部署流水，也不恢复未选中 Version 的 snapshotBuildId；这些完整历史一致性检查保留在原完整聚合读取/写入路径。当前所选记录缺失或不一致仍明确失败，不做降级。

## 验证

### 组件列表与发布扫描（第二批）

- 仅管理页 `COMPONENT_LIST` 改为 `ManagementListPage<ComponentListItem>`；SQL 筛选后 `LIMIT/OFFSET`，不读 Schema/demo/模板/运行配置。
- 组件名、中文名、协议查找键、负责人、场景保留原有参数化 LIKE 语义；类型/协议统一大写，启用筛选保留。
- 默认 20 条、最大 100 条，非法页码明确拒绝。总数与分页在短只读 REPEATABLE READ 事务内查询。
- 页面显示真实 total；本页可引用数和协议数明确标注“本页”。切换分类或搜索回第一页；旧响应不能覆盖新筛选。
- 编辑先读取完整详情和既有发布权限，再填表；详情失败不打开残缺表单。内部 Authoring 与 Skill 绑定候选仍使用原完整查询，不被管理分页截断。
- 发布扫描修正为 keyset + 显式 LIMIT 100。当前 SqlSessionFactory 未配置分页拦截器，不能以 `Page` 入参作为物理分页证据。
- 此次不改变发布历史恢复、校验或写入语义；“仅恢复当前发布记录”仍未完成。

### 已执行检查

- JDK 17 编译通过；前端 TypeScript 与 Vite 构建通过。
- 隔离 PostgreSQL/MyBatis 探针：125 条 Skill 的首尾页、超过 100 条的搜索、状态计数、稳定排序、专员筛选、版本/命名空间隔离、空分类、查询次数与字面量搜索通过。
- 组件 125 条数据：首尾页、筛选、稳定排序、非法 pageSize、字面注入输入、原 LIKE 通配符语义、摘要无大字段通过。
- 发布扫描 225 条数据：3 次实际 SQL，每次最多 100 条；所有资产完整且无重复。探针刻意不装分页插件。
- 第三批独立 PG/MyBatis 回归通过：225 Build + 3 Version + 3 Deployment，只恢复 PRT/ONLINE 所需的 2 Build + 1 Version；根行 1 次、索引 2 批、正文 1 次，共 4 次查询。新读模型扫描 225 根行仍为 3 次 SQL、最多 100 行。
- 同一测试样例的序列化读模型从 1,922,457 bytes 降至 25,779 bytes（约减少 98.7%），新旧两环境结果完全一致。此数值不是线上内存 RSS、SQL 时延或整个接口传输量。
- 精确 PRT 指针、ONLINE 派生快照、环境摘要不匹配、正文篡改、缺失引用、未选中历史记录索引摘要检查、旧内联聚合读取通过；完整发布写入链路未替换。全部数据仅在独立测试库生成。
- 组件管理页的构建产物在本地 Chrome 隔离样例回归：125 条尾页、搜索重置页码、编辑读取详情、慢响应不覆盖新筛选、控制台无运行错误。不是公网联调证据。
- 本地 Vite 开发模式发现既有 SafeJSON 导入错误；生产构建预览正常。本批未扩展修复开发模式。390px 窄屏原有头部布局溢出仍在，不宣称移动端验收通过。
- 探针必须显式指定本机回环地址的独立 `management_query_test` 数据库，运行时会清空该测试库中的五张测试表；不能连接业务库。

```sh
mvn -q -DskipTests compile dependency:build-classpath -Dmdep.outputFile=/tmp/management-query-classpath.txt
java -cp "target/classes:$(cat /tmp/management-query-classpath.txt)" \
  backend/storage/db/tests/ManagementListQueryProbe.java \
  jdbc:postgresql://127.0.0.1:15489/management_query_test management_query_test
```

未跑全仓单测、线上负载测试。隔离探针不等于公网页面部署验收。

## 仍待处理

- Application 的 SQL 分页与轻量列表 DTO。
- 能力中心的完整 SQL 分页、分类过滤前置及轻量发布状态读取。
- 上述查询定型后的执行计划验证与必要索引，不修改已登记的 V001 迁移校验和。

本批不应被称为“所有 M 端慢查询已修完”。
