# 稳定编排与 AI 生成 A2UI 双路径

## 范围

稳定路径保留 `query_skill_dependencies → render_application`。新增
`generate_a2ui(appCode, params, intent)`：`appCode` 必须属于本轮已准入 Skill；它提供
工程侧的数据加载、入参、Action 和当前 Catalog 权限，而不是限制生成的组件树。
专用、隔离的 Deep Agent 根据官方组件 Schema 生成新组件 ID 和布局，不改原资产。
当前支持官方注册组件；未支持的自定义组件明确拒绝，不静默降级。

## 生成与执行

1. 主 Agent 先读取已发布 Application 入参契约；身份、环境和会话作用域由服务注入。
2. 生成 SubAgent 只收到意图、静态组件契约与工程约束，不继承主 Agent 历史、文件系统、
   业务执行工具或通用 `task`。一次模型调用，不自动修复重试。
3. 模型输出现有 A2UI `createSurface/updateComponents` 消息和批准 Action 的位置映射。
   工程数据初始化、LoadBinding、能力调用配置不允许模型生成。工程写入锚点必须保留。
4. 执行服务检查当前 Catalog、官方 Schema、组件引用、数据路径和批准的 Action，再执行
   工程加载。Schema 使用已有官方资源单一来源，不维护另一套 Java/Python字段列表。
   List 子项的新增只读展示字段须同时满足：字段是 `paramsSchema` 中显式声明的叶子
   primitive，且已发布的 required `APP_PARAMS` ShowInputBinding 确实把所属数组写入该
   List 指向的 DataModel 子树。`readOnlyDisplayBindings` 单独列出允许的 `Text.text`
   相对路径及原 List 模板作用域；它不并入通用数据路径或旧相对绑定规则，不授权输入控件、
   Action context、新函数或未声明字段。即使 schema 允许 `additionalProperties`，也不推断
   通配字段；`$ref`/组合 schema 未解析时保守拒绝。生成候选改变 List 模板作用域仍拒绝。
   嵌套 List 的相对 `children.path` 不参与这项新增推导，仍由原相对绑定规则处理。
5. 卡片快照及 GENERATED 定义同一笔卡片存储落库后，才发送可见事件。没有跨服务事务承诺。
6. Action 从已保存定义恢复布局，并重新检查当前源 Application/能力权限。使用最新已发布
   配置，不恢复旧的版本锁；artifact digest 仅用于生成定义完整性，不是版本准入条件。

## 历史与 Workflow

- 和稳定卡片共用 renderer、Assistant UI、按顺序的文字/卡片消息及历史自动恢复。
- 私有候选定义/身份不放进浏览器公开 DTO；页面只增加“AI 生成布局”标识。
- 模型只接收既有业务展示投影和 Action 观测，不把整份组件协议重复加入上下文。
- Workflow 的 native interrupt 重放使用已保存卡片，不重新生成、不重复 LoadBinding。
- 翻页/选择不推进节点；只有批准的终结 Action 成功保存后才能恢复。停止与重复请求语义不变。
- Finalizer 可接受真实完成的 `generate_a2ui` 作为渲染能力的替代证据，不能由模型文本冒充。

## 非目标

不开放模型任意 RPC/HTTP、任意业务写绑定、脚本执行，不自动发布成 M 端资产，
不使用 A2UI 表达 Workflow 图，不新增通用代理、自动回退或隐式重试。

## 准出

源码验证、部署和公网验证分别记录。需要验证稳定卡片、生成卡片、分页/跨页选择/输入框
回填、刷新恢复、Workflow 暂停/确认/唯一恢复，以及错误/越权/无效 Schema 拒绝。
未完成公网验证之前，不把该能力记为已验收。
