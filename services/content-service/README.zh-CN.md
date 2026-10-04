# A2Flow 内容业务服务

本目录实现“阅读到创作”MVP 的 Python 业务内核，只保存项目、素材、产物、用户确认和写请求回执。它不保存第二份聊天消息、模型 Tool 过程或 Workflow 状态。

## Typed 接口

`ContentService(repository)` 提供 11 个同步方法：项目 create/list/get、素材 save/get、产物 save/get、阅读/选题/稿件确认和稿件导出。

Markdown 原文可直接导出；TXT 使用 CommonMark 解析器按 token 提取文本，保留普通下划线、行内代码和代码块内容，不使用全局正则删除正文字符。

每个方法接收 `TrustedContext(user_id, environment, request_id, trace_id)`。`user_id` 支持完整 signed 64-bit，只能由已认证的内部传输层构造，不能从业务字段或模型输出读取。

固定文档使用 `ReadingBrief`、`TopicPlan`、`Manuscript` dataclass。JSONB 只是这些 DTO 的持久化表示，不是通用 `dict[str, Any]` 服务接口。

## PostgreSQL

仅支持 PostgreSQL。仓储在构造时固定 DSN、精确 database 名和 `PRT` / `ONLINE` 环境：

```python
repository = PostgresContentRepository(
    conninfo,
    environment=Environment.PRT,
    database="a2flow_content_test",
)
repository.setup()        # 显式迁移，不在请求路径自动建表
repository.check_ready()  # Host 启动前只读检查，不补表或降级
service = ContentService(repository)
```

包内迁移 `a2flow_content/migrations/001_content_schema.sql` 包含五张业务表。PRT / ONLINE 绑定不同数据库；请求环境与实例不一致时拒绝，不跨环境回退，也没有 SQLite / MySQL / 内存生产兜底。

写操作在同一事务内完成：

- `(user_id, operation, request_id)` 的事务级 advisory lock 和回执去重；
- 同 requestId 不同 canonical payload 返回 `IDEMPOTENCY_CONFLICT`；
- 素材和确认写入在项目行锁内串行更新内部 revision，不接收调用方项目版本；
- 当前指针、业务记录和回执一同提交或回滚；
- 创建项目回执保存 typed 响应快照，重放不会返回后来改变的项目状态。

所有读取都按 owner 查询；无权访问与不存在统一返回 `CONTENT_NOT_FOUND`。产物引用必须属于同一 owner/project 且 revision 精确匹配。

## 内容证据

- 非模型建议的阅读观点引用必须出现在关联素材正文中；非空字符串本身不算证据。
- 选题的 `source_point_ids` 必须来自关联的真实阅读简报。
- 稿件 citation 必须与精确 `input_refs` 对应。
- 素材内容始终是数据，其中的文字不会获得 Tool、身份或环境权限。

## 验证

```bash
ruff check src tests
mypy src
pytest -q
```

真实 PostgreSQL 测试必须显式提供隔离测试库：

```bash
A2FLOW_CONTENT_TEST_DSN='postgresql://.../a2flow_content_test' \
A2FLOW_CONTENT_TEST_DATABASE='a2flow_content_test' \
pytest -q tests/test_postgres_integration.py
```

源码或隔离数据库通过不代表 gRPC Host 已部署，也不代表真实模型、M 资产、A2UI 或 Workflow 已验收。
