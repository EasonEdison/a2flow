# Workflow Registry Python 模块与校验栈候选

## 1. 状态和边界

- 状态：`PROPOSED / DOC_RESEARCH_ONLY`
- 适用基线：`SW-P1-20260907.2 + ENG-01`
- 共享输入：`SW-P1-SUBSET-01` 已批准 corrected snapshot `a1cb44e88ce5bb603c62b4618804c78ae0d5585c` 中 exact `skillKey/use_skill` 相关闭包作为命名实现依赖；wire field 仍为 `SW-CONTRACTS-P1-CANDIDATE.1`。Workflow graph/context/control/events 仍为 `PROVISIONAL`，本文件不把它们升级为已批准 graph revision。
- 本文件只给出 `services/workflow-registry/` 的候选包布局、依赖取舍、校验流水线和测试门禁。
- 未创建服务目录，未修改根 `pyproject`/lock，未安装包，未替换系统 Python，也未启动进程或数据库。

## 2. 推荐结论

采用三层组合：

1. 共享 JSON Schema 是传输/发布边界的唯一结构权威，Workflow 适配器按共享 artifact 声明的 `$schema` 方言校验，不能自行升级或复制一份竞争 schema。
2. Pydantic 仅把已通过共享 schema 的 payload 转为严格、不可静默放宽的内部域模型；禁止未知字段和隐式容错，不覆盖共享 schema 的含义。
3. NetworkX `DiGraph` 提供 cycle、可达性、ancestor/descendant 和确定性拓扑遍历所需的成熟算法；Workflow 自己只实现 decision/merge、split/join、failure requirement 等领域约束。

Runtime 继续用 LangGraph 编译已接受的发布图。M 侧 validator 不导入 LangGraph/Deep Agents，也不实现执行、checkpoint、interrupt、retry 或调度。

## 3. 方案比较

| 方案 | 组成 | 优点 | 主要风险 | 结论 |
| --- | --- | --- | --- | --- |
| A | JSON Schema + Pydantic + NetworkX | 协议、域模型和图算法分层；覆盖 ancestor、可达性、拓扑排序等现成能力；减少自研通用算法 | 增加一个纯 Python 图依赖；需要先证明版本、资源和根锁文件兼容 | `RECOMMENDED` |
| B | JSON Schema + dataclasses + 标准库 `graphlib` | 依赖更少；`TopologicalSorter` 可做 cycle/topological 检查 | ancestor/descendant、region closure、稳定定位仍需自行实现和长期维护 | 仅在 main-brain 拒绝 NetworkX 依赖后重新评估，不自动降级 |
| C | Pydantic validators + 手写 traversal | 初始文件少 | 把协议与领域校验混在一起，重复图算法，错误定位和复杂度难审计 | `REJECTED` |

`graphlib.TopologicalSorter` 只能替代部分拓扑能力，不是 NetworkX 的等价 drop-in。若选择 B，必须先列出新增算法、复杂度和 mutation/property tests，再由 main-brain 审查；Composer 不自行切换。

## 4. 候选包布局

以下目录仅是 ENG-01 下的精确提案，不是本轮已实现文件：

```text
services/workflow-registry/
  src/skillweave_workflow_registry/
    models.py
    validation/
      issues.py
      pipeline.py
      topology.py
      regions.py
    ports/
      contracts.py
      publication.py
      repository.py
    adapters/
      contracts_jsonschema.py
      postgres.py
  tests/
    contract/
    unit/
    integration/
```

职责边界：

- `models.py`：严格内部域模型，不声明共享 wire schema。
- `contracts_jsonschema.py`：加载 contracts owner 发布的 schema/bundle，按其中声明的 dialect 校验；不复制或改写共享定义。
- `topology.py`：把 node/edge identity 投影到 `DiGraph`，调用成熟 DAG/reachability/ancestor 能力。
- `regions.py`：验证 decision candidate/MERGE 与 parallel split/JOIN 的闭合、唯一归属和首版不嵌套规则。
- `issues.py`：内部 issue 表示与确定性排序；共享 issue envelope/code 未命名前不对外冻结。
- `pipeline.py`：编排纯校验阶段，不做数据库、resolver 或 Runtime 调用。
- `ports/contracts.py`：隔离共享 schema/identity/version 输入。
- `ports/publication.py`、`ports/repository.py`：定义应用层端口，不把 PostgreSQL 或共享 publication 细节写进域校验器。
- `adapters/postgres.py`：后续 PostgreSQL-only 实现位置；不属于第一份纯 validator 切片。

模块自身不创建第二份 lock，也不自动成为常驻服务。根依赖和进程组合仍由 main-brain 单一协调。

## 5. 校验流水线

校验顺序必须稳定，前一阶段失败时不得产生发布 artifact：

1. **输入限额**：在构图前检查 nodes、edges、region depth 等已获批数值上限。具体值来自 named graph revision/policy，本文件不填猜测值。
2. **共享结构校验**：按 shared schema 的 `$schema` 方言执行；当前候选使用 Draft 4 只为服务器现状下的有界检查，Workflow 不擅自改成 Draft 2020-12。
3. **严格域模型解析**：拒绝未知字段、错误枚举和静默类型 coercion；Pydantic 不得让 schema 已拒绝的数据重新合法。
4. **基础图校验**：identity 唯一、引用存在、START/FINALIZER/END 数量、全可达、无环和必需入/出边。
5. **领域 region 校验**：decision candidates、CONDITION_MERGE、parallel split/JOIN 闭合、分支唯一归属、交叉/嵌套禁止、failure requirement 边界。
6. **外部引用校验**：通过只读 resolver/contract port 校验 exact `skillKey`、selection Application 等引用；纯 graph validator 不直连网络或数据库。
7. **确定性输出**：候选内部排序键为 `(phase, nodeKey, edgeKey, regionKey, code)`；最终公共 issue schema/code 必须服从 named shared revision。

复杂度目标：基础 DAG、可达性和单次 ancestor/descendant 查询保持 `O(V + E)`；region 检查受已批准 graph size/depth 上限约束。实现不能为每个规则无界重复扫描，也不能以递归深度承载未受限输入。

## 6. 依赖研究快照

以下是 2026-09-07 读取官方项目元数据所得候选，不是已写入 lock 的 pins，也不是服务器兼容结论：

| 用途 | 候选版本 | 许可证 | 官方 Python 要求 | 采用边界 |
| --- | --- | --- | --- | --- |
| 严格域模型 | Pydantic `2.13.5` | MIT | `>=3.9` | 仅内部模型；共享 schema 仍是权威 |
| JSON Schema 执行 | jsonschema `4.26.0` | MIT | `>=3.10` | 支持多 dialect；必须按共享 artifact 选择 validator |
| DAG 算法 | NetworkX `3.6.1` | BSD-3-Clause | `>=3.11`（排除 Python 3.14.1） | 仅静态图算法，不执行 Workflow |
| 测试运行器 | pytest `9.1.1` | MIT | `>=3.10` | dev/test 候选 |
| 可选 property test | Hypothesis `6.167.1` | MPL-2.0 | `>=3.10` | 非首个必需依赖；先做许可证审查 |
| 后续 PostgreSQL adapter | psycopg `3.3.5` | LGPL-3.0-only | `>=3.10` | 不进入首个纯 validator 切片；单独审查部署/许可证 |

Python `3.11+` 是当前模块兼容候选：它由 NetworkX 的最低要求决定，也与当前 Deep Agents PyPI classifiers 覆盖 3.11+ 的信号一致。`SW-P1-SUBSET-01` 把 Python 3.11 定为第一验证目标并允许列明 owner 复用 Runtime 环境已有 Pydantic 2.13.5，但没有把 Workflow owner 或本候选依赖栈纳入实现放行。这仍是跨模块兼容输入；Runtime/main-brain 选择并实测精确 Python、Deep Agents、LangGraph 和根锁文件组合。服务器现有 Python 3.6.8 只能运行当前标准库 fixture/checker，不能证明候选栈可安装或可执行；PY-01 的主机变更仍仅由 Runtime 执行。

## 7. 测试与证据门禁

第一份获批实现应按 TDD 交付纯 validator，不先接数据库：

1. 先把现有有效图输入产品 validator，断言 `valid=true`、无 ERROR issues 和确定性 normalized graph/digest 输入。
2. 对 `phase1-validation-cases.json` 的每个 mutation 实际修改图并调用产品 validator，断言稳定 issue code 与 node/edge/region path；当前 checker 仅检查 case 目录存在，不能冒充这些测试。
3. 增加 repeated-order 测试：打乱 nodes/edges 输入顺序，语义结果和 issue 排序保持确定。
4. 用 fake resolver port 验证 exact `skillKey`、selection Application 引用和错误传播；不依赖网络、数据库或另一常驻服务。
5. 先用显式 example tests 锁定已确认边界，再把 Hypothesis 作为可选 test-only 增强，用于生成 DAG/非法 region；许可证与资源成本未审查前不得变成强制依赖。
6. A→B→C ancestor context、A waits/B1→B2、join、retry、stop 是 Runtime 行为测试，不由 M 静态 validator 的绿测替代。
7. named revision、根依赖 pin、Python 兼容、包安装、许可证、峰值内存/耗时均有实际证据后，才能开始 PostgreSQL adapter 和发布集成。

## 8. 开源依据

- [Pydantic PyPI](https://pypi.org/project/pydantic/)
- [jsonschema PyPI](https://pypi.org/project/jsonschema/)
- [NetworkX PyPI](https://pypi.org/project/networkx/)
- [NetworkX DAG algorithms](https://networkx.org/documentation/stable/reference/algorithms/dag.html)
- [Python graphlib](https://docs.python.org/3/library/graphlib.html)
- [pytest PyPI](https://pypi.org/project/pytest/)
- [Hypothesis PyPI](https://pypi.org/project/hypothesis/)
- [Psycopg PyPI](https://pypi.org/project/psycopg/)
- [Deep Agents PyPI](https://pypi.org/project/deepagents/)

这些页面证明的是公开元数据/能力，不证明项目已安装、服务器兼容、资源达标、shared revision 获批或 Runtime 可用。
