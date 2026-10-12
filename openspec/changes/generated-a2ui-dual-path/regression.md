# 双路径 A2UI 与管理端分页回归

## 2026-10-13 部署范围

- 源码基线 `c0167966bacbbe5a8757bb88853a0e0c85a2064d`，两个 main 已同步。
- 运行态最终修复版本 `1527d772e0922592680b51fe1acfefb45fe76e18`，execution/runtime/bside 均部署 `scoped-1527d77`；M 与前端产物仍为上述基线，无后续界面改动。
- Java 管理端、管理端静态、数字员工静态、Python Chat / Workflow Runtime / A2UI 执行服务已部署。
- 本机完成 Java/前端构建；服务器只接收产物和增量镜像，未修改数据库结构或删除业务数据。
- 来源定义保留在卡片私有元数据；公共消息仅增加生成来源标记，复用原有渲染、操作、历史链路。

## 已通过

| 范围 | 实际证据 |
| --- | --- |
| 管理端分页 | 真实业务能力共 14 条，pageSize=10 的尾页为 4 条；尾页搜索 `content.people` 回首页显示 2 条 |
| Application 列表 | 真实列表 4 条，搜索 `people` 为 1 条，编辑可完整恢复该 Application 详情 |
| 大数据分页 | 隔离 PG/MyBatis 的 125+125 条能力/Application 分页、尾页、关键词和状态筛选通过；不是生产压测 |
| Chat 生成 | 新会话依次调用 use_skill、query_skill_dependencies、generate_a2ui，界面显示“AI 生成布局” |
| 真实数据 | people-selector 使用实际 LoadBinding，total=15、pageSize=5，初始为第 1/3 页 |
| 跨页 Action | 第 1 页选林知夏、第 2 页选唐予宁，回填两个姓名与脱敏电话；未自动发送消息 |
| 历史 | 页面刷新后恢复生成卡片、第 2 页及唐予宁勾选；可继续调用上一页 |
| 持久化 | 会话 35 保存一份 GENERATED 卡片、私有 generatedDefinition、2 条候选消息；3 次 Action 均 FINISHED |
| Workflow 混合路径 | run `d6cde8931de24eb68e00b49eb2bd52c2`：生成阅读卡 → 稳定选题卡 → 稳定稿件卡，三次页面确认后数据库 SUCCEEDED |
| 人工确认门禁 | 各节点先等待卡片操作，选值/编辑时不推进，确认成功后才进入下一节点；首卡刷新恢复后仍可确认 |
| 无重复提交 | 上述 run 三张卡均 COMPLETED，各只有 1 条 FINISHED Action；只有阅读卡保存 generatedDefinition，后两张来源 PUBLISHED |
| 终态历史恢复 | 完成后刷新进入“我的运行”，三节点一次性恢复 7/7/8 次工具调用；阅读勾选 rp-3/rp-4、编辑选题标题及稿件标题恢复，全部历史卡片输入/确认按钮禁用 |
| 页面与运行状态 | 终态页面无 console warn/error；三个更新服务 running、restart=0、OOMKilled=false；最终 available 481 MiB（瞬时值） |

Chat 卡片标识：`card:73c5f13a38b4a8cf1938c3028195b1431fa70c2aca8ff4e23536d360a1f467b8`。
人员均为已有虚构演示数据，未读取真实通讯录。

## 验收中发现的问题与边界

1. 首轮只切换 Workflow Runtime，遗漏普通 Chat 所在 Bside Python；真实页面工具缺失后已补齐 Bside 同版本镜像。旧失败会话保留，不能作为生成成功证据。
2. Workflow 第一轮在卡片生成之前遇到模型非法完整工具 JSON，明确失败，未推进后继节点；不增加自动修复/重试。
3. Workflow 第二轮调用 generate_a2ui，被 `A2UI_GENERATION_DATA_PATH_NOT_ALLOWED` 拒绝。只读真实发布源 identity 验证同样失败：List 模板的 `claim`、`evidenceQuote`、`explanation` 相对路径被错误排除。`f6e517a` 修复 ChildList 路径与模板作用域后，真实发布源 identity 通过。
4. 第三轮候选消息结构不合法；`6a640ee` 增加消息 envelope Schema、细分错误，以及专用生成器 JSON Output。普通模型调用不变。真实 design-only 生成 2 条消息/1 条 ActionPlacement，并经线上执行服务原样校验通过，没有执行 LoadBinding 或 Action。
5. 第四轮在动态展示 `evidenceLocator`/`modelSuggestion` 时仍拒绝数据路径。只读发布源证实这些字段在 `paramsSchema.points.items.properties` 中声明，且 required APP_PARAMS `/points` 映射到 DataModel `/points`，但旧规则只允许原模板展示过的字段。`1527d77` 已补同列表作用域的独立只读展示许可，不开放未知字段、输入写绑定或新 Action。真实模型明确生成这两个字段的样例再次通过线上原样校验；新的 Workflow 已生成阅读卡片并等待确认。

两个独立失败运行：`28b9632caa3b478b8296ed9ace38c07c`、`6403aa20d1854911897045cd18d538a1`。保留现场，不重放已执行业务操作。
后续失败运行 `884cd158a18c4d179156f61b577d28a2`、`6026e34cc8224e168b784fda03b5da2f` 同样保留；未保存或展示不合法候选卡片。

## 定向验证

- 生成器 SDK 隔离/无继承工具与历史、单次调用、无自动修复、JSON 模式仅 opt-in、Workflow 已存卡片恢复与 Finalizer 事实门禁：7 项通过。
- 执行侧消息 envelope、字段/组件/树/Action 约束：此前 37 项通过。
- 新增只读展示许可：21 项定向测试、strict mypy/Ruff 通过；限定同列表作用域的显式基础类型字段，不推断复杂 Schema 或新增写权限。
- 新生成器 strict mypy、Ruff、变更敏感扫描通过；旧 adapter 全测试因验证环境缺 `langchain_deepseek` 未跑，不表述为全量通过。
- 02:24 服务器可用内存 589 MiB，三个更新服务 restart=0、OOMKilled=false；瞬时值，不是容量/压测结论。

## 验证边界

- 未开放任意 RPC、HTML、脚本或模型自创业务绑定。
- 首版生成组件为当前 Catalog 的官方允许子集；不宣称支持所有自定义/媒体组件。
- 不自动把生成定义发布为管理端资产。
- 未进行全仓测试、全面压测或移动端专项验收。
- 最终 Workflow 的三步确认及终态历史恢复已通过；未导出稿件、未对外发布。
