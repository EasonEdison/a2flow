# Python Engineering Standards / Python 工程规范

This document defines the minimum standard for new or materially changed Python production code in A2Flow. It is an incremental adoption policy: a touched boundary must become clearer and safer, while unrelated legacy modules are not rewritten merely to improve a metric.

本文定义 A2Flow 新增或实质修改的 Python 生产代码最低标准。规范采用渐进式落地：修改到的边界必须更清晰、更安全，但不能为了指标而顺手重写无关旧模块。

## 1. Representation by boundary / 按边界选择表达

| Boundary / 边界 | Required representation / 推荐表达 | Purpose / 目的 |
| --- | --- | --- |
| HTTP request | strict Pydantic model with `extra="forbid"` | Parse and reject untrusted wire input once / 集中解析并拒绝不可信输入 |
| Domain value | frozen dataclass and `Literal` identities | Preserve invariants without framework coupling / 保持领域不变量且不绑定框架 |
| Serialized response or stored shape | `TypedDict` plus explicit conversion | Make field names and optionality reviewable / 让字段与可选性可审查 |
| Database and service dependency | narrow `Protocol` port | Depend on required behavior rather than a concrete driver / 依赖最小行为而不是具体驱动 |
| Recursive JSON | shared `JsonValue` and `JsonObject` aliases | Avoid ambiguous `dict` and scattered aliases / 避免模糊字典和重复类型 |

Pydantic belongs at an untrusted transport boundary. Domain validation remains in domain constructors so HTTP, CLI, tests, and internal callers share the same rules and error codes.

Pydantic 只放在不可信传输边界。领域校验继续由领域构造器负责，使 HTTP、CLI、测试和内部调用共享同一套规则与错误码。

Management drafts are a special stored-input boundary. Their Pydantic models validate identity, field containers, relation-bearing values, and prohibited material before repository I/O, but they do not normalize or replace the submitted JSON document. An author may save a structurally safe yet incomplete draft; publishability remains the responsibility of the asset validator. Unknown extension fields are preserved unless the asset contract explicitly forbids them. Stable management error codes must survive the migration from manual dictionary inspection to typed models.

管理草稿是一类特殊的持久化输入边界。对应的 Pydantic 模型在写仓库前校验身份、字段容器、关联字段与禁止写入的内容，但不得把提交的 JSON 重新导出后替换原文。作者可以保存结构安全但尚不完整的草稿；能否发布仍由各资产校验器判断。除非资产契约明确禁止，未知扩展字段必须保留。从手写字典检查迁移到类型模型时，既有管理错误码必须保持稳定。

## 2. Shared asset kernel / 统一资产内核

- Asset kinds use one shared identity: `SKILL`, `ABILITY`, `COMPONENT`, `APPLICATION`, and `WORKFLOW`.
- Stable asset identity, retained version identity, draft revision, and serving selection are different concepts and must not share an ambiguous string.
- Authoring relations use one generic directed relation shape. The source draft owns the relation snapshot revision; a new draft revision replaces the complete outgoing set for that revision.
- Authoring relations do not replace immutable dependency/version evidence retained by a published asset.

- 资产类型统一为 `SKILL`、`ABILITY`、`COMPONENT`、`APPLICATION`、`WORKFLOW`。
- 稳定资产身份、保留版本身份、草稿修订号和生效选择是不同概念，禁止混成一个含义不明的字符串。
- 编辑态关联使用统一的有向 Relation 结构；关联快照修订号归属源草稿，新草稿修订完整替换该修订的出边集合。
- 编辑态关联不能替代发布资产保留的不可变依赖与版本证据。

## 3. Validation and casts / 校验与类型收窄

- Do not use `Any`, broad `dict`, `# type: ignore`, or unchecked `cast` as a default design tool.
- A database row is untrusted input. Check row width, scalar types, enum membership, JSON object shape, and digest before constructing a domain value.
- A `cast` is allowed only after an adjacent runtime check or when adapting a library API whose runtime contract has already been verified.
- Keep decimal-string `userId` at JSON/HTTP boundaries and signed integers internally. Never convert through floating point.
- Errors exposed across a boundary are stable codes; do not leak SQL, connection strings, raw payloads, or credentials.

- 禁止默认使用 `Any`、宽泛 `dict`、`# type: ignore` 或无校验 `cast`。
- 数据库行属于不可信输入；构造领域对象前必须检查列数、标量类型、枚举成员、JSON 对象形状和摘要。
- `cast` 只能紧邻运行时检查，或用于已核验运行时契约的第三方库适配。
- JSON/HTTP 边界的 `userId` 使用十进制字符串，内部使用有符号整数，禁止经过浮点数转换。
- 跨边界错误使用稳定错误码，不泄露 SQL、连接串、原始载荷或凭据。

## 4. Readability and ownership / 可读性与职责

- Files should have one primary responsibility. Transport DTOs, domain values, persistence ports, and adapters live in separate modules.
- Names describe product concepts, not implementation accidents. Prefer `PublicationTarget` and `AssetIdentity` to anonymous mappings.
- A function either validates/converts or performs an operation; avoid combining unrelated lifecycle decisions in one large function.
- Comments explain a non-obvious invariant or boundary. They must not restate code line by line.
- Preserve existing public error codes, canonical serialization, optimistic concurrency, environment isolation, and publication semantics during refactoring.

- 文件应只有一个主要职责，传输 DTO、领域值、持久化端口和实现适配器分模块放置。
- 命名表达产品概念而不是实现偶然性；优先使用 `PublicationTarget`、`AssetIdentity` 等明确对象。
- 函数负责校验转换或执行操作之一，避免在一个大函数中混入多个无关生命周期决策。
- 注释解释不直观的不变量和边界，不逐行复述代码。
- 重构必须保持已有错误码、规范化序列化、乐观锁、环境隔离与发布语义。

## 5. Reference implementation boundary / 参考实现边界

When behavior is informed by another implementation, record a concept mapping and independently implement the required invariant in this repository. Do not copy source text, comments, DDL, tests, package names, internal service identifiers, credentials, or proprietary adapters. Acceptance is based on A2Flow contracts and tests, not textual similarity.

参考其他实现时，应记录概念映射，并在本仓库独立实现需要的不变量。不得复制源代码文本、注释、DDL、测试、包名、内部服务标识、凭据或专有适配器。验收依据是 A2Flow 契约与测试，而不是文本相似度。

## 6. Required gates / 必须门禁

For the current typed subset:

```bash
make quality-python
git diff --check
```

`quality-python` runs pinned strict mypy plus Ruff lint and formatting. Every expansion of the typed subset must list production files explicitly, add focused behavior regression, and state what remains outside strict coverage. Test success, source delivery, deployment, and runtime acceptance are reported separately.

`quality-python` 使用固定版本的 strict mypy 与 Ruff 检查。每次扩大类型覆盖都必须显式列出生产文件、增加聚焦行为回归，并说明尚未纳入 strict 的范围。测试通过、源码交付、部署完成与运行态验收必须分别陈述。
