# Phase 1 准出状态

## 结论

`NO READY`

当前只完成统一基线对齐中的设计修订和非规范 fixture 准备。没有获批 shared graph revision、workflow-registry 实现、PostgreSQL 集成、LangGraph 行为证据或部署结果。source merge 不能表述为产品或 Runtime READY。

## 门禁

| Gate | 要求 | 当前状态 | 当前证据 |
| --- | --- | --- | --- |
| G0 ALIGN | 对齐 `SW-P1-20260907.2` 并移除冲突旧方案 | `PARTIAL` | proposal/design/spec 已修订，待本批提交与 main-brain review |
| G1 CONTRACT | shared graph/context/resolver/interaction/result/control revision 获批 | `NO READY` | 本任务仅提交消费者需求和非规范 fixture |
| G2 REGISTRY | `services/workflow-registry/` 完成最小实现和 PostgreSQL-only 测试 | `NO READY` | 尚未获放行，目录未实现 |
| G3 GRAPH VALIDATION | sequence/decision/MERGE/parallel/JOIN/Finalizer validator 通过 | `NO READY` | 仅项目 fixture 自检，不是产品 validator |
| G4 RUNTIME MAPPING | Python LangGraph 证明 A waits、B1→B2、JOIN waits A | `NO READY` | 无 Runtime spike 输出 |
| G5 INTERACTION | node-bound AI/A2UI choice、version ingress、A2UI-only retry 通过 | `NO READY` | 仅 planned contract tests |
| G6 FAILURE/STOP | allow-skip/required failure、stop/Finalizer 事实边界通过 | `NO READY` | 无运行证据 |
| G7 MULTI-INSTANCE | PostgreSQL 下两个实例竞争写入/控制请求正确 | `NO READY` | 无集成证据 |

## 当前允许声明

- 已按统一基线提出 sequence、AI condition、受限 parallel、condition MERGE 和 explicit JOIN 的消费者图候选。
- 已定义 A waiting/B1→B2、join、allow-skip/required failure、A2UI-only retry 和 Finalizer 的 planned assertions。
- fixture 自检通过后，只能声明“示例结构检查通过”，不能声明 Runtime 语义通过。

## READY 前最低证据

1. main-brain 指定已批准 shared contract revision，并确认 workflow-registry 实现范围和语言/包布局。
2. 产品 validator 对有效/无效 fixtures 给出可复用输出，PostgreSQL-only repositories 和双实例并发验证通过。
3. Runtime 以明确 Python/Deep Agents/LangGraph 版本在 PostgreSQL checkpointer 上证明 A waits/B1→B2/join。
4. AI 不确定 A2UI 选择、版本失配 reset、A2UI-only retry、required failure、stop/Finalizer 门禁均有真实 method/params/data/字段断言。
5. 所有必需 gate 从 `NO READY` 变为有证据的通过状态；否则不得归档。
