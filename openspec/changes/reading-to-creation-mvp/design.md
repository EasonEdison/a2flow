# 阅读到创作助手：业务与技术设计

状态：2026-09-23 用户确认方案，修正为仅 M 端使用 Java，其余服务使用 Python。字段和接口是目标契约，实施前须对照现有 RPC / 发布 / A2UI 契约复用，不代表已有实现。

## 1. 系统职责

- M 端：维护并发布业务能力、三个 Skill、三个 Application、引用的组件和一个 Workflow；真实数据库存储，不把场景写死在前端。
- Python Runtime：通过 Deep Agents 执行 Skill，通过 LangGraph 执行外部 Workflow；不直接查询内容业务数据库。
- Python 执行服务：解析已发布能力、校验参数、注入可信 userId / 环境，并按既有 RPC 机制调用业务服务。Java 仅保留在 M 端；实施前核对现有执行链路，若仍有 Java 运行态承接，明确列出迁移范围，不宣称已经完成切换。
- 新增内容业务服务：独立 Python 服务，共用既有开源 RPC 技术栈，负责素材、项目、内容版本、确认和导出。数据访问复用项目 Python PostgreSQL 基础设施，不使用 MyBatis；保持类型明确的请求/响应、业务服务和数据库访问边界。具体驱动与迁移工具在核对现有依赖后确定，不额外引入一套重复基础设施。
- 外部适配器：后续包装文章读取、视频处理和发布服务；不把提供方细节泄露给 Skill。首版不需要外部提供方即可完整使用。

调用顺序为：`Skill → execute_ability → 执行服务 RPC → 内容业务服务 RPC → PostgreSQL`。
渲染顺序为：`Skill → render_application → 已发布 Application → A2UI Surface`。
卡片操作经宿主 Action 入口解析已发布 ActionBinding，再调用业务能力，不要求每次点击都重新调用模型。

内部链路统一 RPC，沿用已建立的服务认证。userId 标识操作人，不代替服务认证；前端和模型不能自选可信 userId。将来外部提供方仅支持 HTTP 时，由内容业务服务适配，不能把内部调用悄悄改回 HTTP。

## 2. 数据库设计

首版建议复用 PostgreSQL 实例、建立内容服务独立 database/schema 和最小权限账号，不另起数据库引擎。PRT 与 ONLINE 分库存储业务数据，不因 userId 灰度跨环境读取。最终数据库名称与连接配置在部署阶段核实。

| 表 | 主要字段 | 约束与含义 |
| --- | --- | --- |
| content_project | id、user_id、title、audience、output_format、current_selection_id、current_manuscript_id、revision、created_at、updated_at | 用户的创作工作集；revision 用于并发修改检测，不代替 Workflow 状态 |
| content_source | id、project_id、user_id、revision、title、source_url、body、digest、created_at | 素材不可变版本；URL 仅记录出处；正文 TEXT 存储 |
| content_artifact | id、project_id、user_id、kind、revision、body_json、body_markdown、input_refs、origin、created_at | READING_BRIEF / TOPIC_PLAN / MANUSCRIPT；输入引用精确到素材/产物版本；区分模型生成与用户编辑 |
| content_confirmation | id、project_id、user_id、artifact_id、decision_type、selection_json、created_at | 记录选了哪些观点、哪个选题、哪份稿件已定稿；不靠模型文字判断用户已确认 |
| content_request_receipt | user_id、operation、request_id、payload_digest、result_ref、created_at | 内容写操作去重；同 requestId 不同参数报冲突，不冒充成功 |

主键建议 UUID；user_id 为 BIGINT（signed 64-bit），JSON/协议边界按既定十进制字符串传输。外键、唯一键和索引在 DDL 中落实：项目所有者查询索引、同项目同类型版本唯一约束、业务请求唯一约束。访问子资源也必须校验所属 userId，不能仅凭 UUID 放行。

body_json 用于结构化内容，不塞原始 Provider 响应或全部 Tool 历史。输入引用、选中标识和正文是业务事实；聊天、模型消息、工具调用过程仍由现有 Deep Agents/Runtime 持久化管理。

每次确认在内容服务自己的事务内保存确认记录、更新项目当前指向并写入请求回执。Workflow 不承担业务事务，不做跨服务回滚。重新开始产生新运行和新的业务操作请求，不扫描或补偿上一轮成功结果；同一次操作重复送达才使用原 requestId 去重。

更换素材/选题不会静默覆盖旧稿件。旧产物仍关联其旧输入版本；界面明确展示来源。首版重新生成走新的 Skill 执行或新的 Workflow，不能把旧稿件伪装为已基于新选题生成。

## 3. 业务能力契约草案

公共可信上下文：userId、environment、requestId、traceId，由宿主/执行服务注入，不作为模型可填写的业务字段。表中是业务输入，不包含身份。

| actionCode | 输入要点 | 返回要点 | 副作用 |
| --- | --- | --- | --- |
| content.project.create | title、audience、outputFormat | projectId、revision | 创建项目 |
| content.project.list | page、pageSize | list、total、page、pageSize | 只读自己的项目 |
| content.project.get | projectId | 项目、素材和当前产物引用 | 只读 |
| content.source.save | projectId、title、body、sourceUrl、expectedProjectRevision | sourceId、revision、digest | 保存素材版本 |
| content.source.get | sourceId | 正文、标题、出处、版本 | 只读 |
| content.artifact.save | projectId、kind、内容、inputRefs | artifactId、revision | 保存生成或编辑版本 |
| content.artifact.get | artifactId | 结构化内容、正文、输入引用 | 只读 |
| content.reading.confirm | projectId、artifactId、selectedPointIds、userNotes、expectedProjectRevision | confirmationId、已选素材 | 保存阅读选择 |
| content.topic.confirm | projectId、artifactId、topicId、editedTitle、editedAngle、expectedProjectRevision | confirmationId、选题单 | 保存选题 |
| content.manuscript.confirm | projectId、artifactId、expectedProjectRevision | confirmationId、定稿版本 | 保存定稿事实 |
| content.manuscript.export | artifactId、format | filename、mediaType、文本内容 | 只读 |

实际 RPC 使用类型明确的请求/响应 DTO；以上逻辑能力可复用同一个服务，不要求每个 actionCode 一个新服务。业务拒绝、版本冲突、资源不存在、RPC 不可达分别表达，不能统统变成空内容成功。

实施细化：RPC 的 `ArtifactBody` 使用 oneof 区分 `ReadingBrief`、`TopicPlan`、`Manuscript`，分别包含观点与依据、候选选题、稿件与引用。模型和 M 端配置面对普通嵌套对象，不需要生成 Base64 或 JSON 字符串。数据库 `body_json` 是经过这些固定 DTO 校验后的 JSONB，不是任意字典入口。确认结果也使用明确字段。项目增加 `current_source_id` 引用当前素材版本，与当前选题/稿件指向一起支持重新打开项目。

导出只读取当前用户可访问的指定版本，浏览器下载文本；不新增公网文件桶或永久下载链接。模型负责分析和生成，内容服务负责验证、保存和读取，不在该服务里再建第二个 Agent。

## 4. 三个 Skill 和 Application

### 4.1 阅读理解

Skill 建议 code：`reading-material-analysis`。读取指定素材，根据任务给出有稳定标识的观点、原文片段/段落依据和解释。引用必须能在该素材版本中定位；找不到依据时明确标记为模型建议，不伪造引文。

Application：`reading-point-selector`。显示观点列表、出处与补充输入，用户选择后提交 `confirmReading`。空选择不通过。确认接口落库成功后才完成交互；失败保留选择并显示错误。

### 4.2 选题策划

Skill：`content-topic-planning`。使用已确认阅读材料，也支持用户在 Chat 中直接提供材料；建议生成 3 个选题，但不是 Workflow 路由节点。每项有标题、表达角度、目标受众和依据。

Application：`content-topic-selector`。单选选题并允许编辑标题/角度，提交 `confirmTopic`。用户确认内容是后续写作依据，模型不能自行改选。

### 4.3 内容成稿

Skill：`content-draft-writing`。输入选题与资料，生成图文正文或口播稿，保存后渲染。输出保留来源引用；不将原文大段重排冒充原创。

Application：`content-manuscript-editor`。编辑、Markdown 预览、保存草稿、确认定稿、导出。保存草稿只生成业务版本，不完成必需交互；确认定稿才完成交互。编辑未保存时，确认/导出需先保存或明确提示，不能下载旧内容冒充新内容。

三类 Application 均为 INTERACTIVE；展示成功不等于 Skill 完成。ActionBinding 分别配置结果成功条件，只有确认动作设置 `completeWorkflowInteractionOnSuccess=true`。Finalizer 基于真实确认结果判断完成，不推翻业务事实。

## 5. 组件、绑定与发布

先盘点当前组件中心和 B 端渲染器，选择已真实实现的布局、文本、选择、输入、按钮和 Markdown 展示组件。需要的编辑控件若不存在，先实现并注册 Catalog，再允许 Application 编译引用；不为效果图虚构可用组件。

Skill 绑定业务能力和 Application、Application Action 绑定能力，均保存到既有通用 relation 表，以 type 区分关系。不创建独立的“内容场景资产关联表”。以上业务项目表也不复用资产 relation 表存正文。

M 端手工创建并验证后发布 PRT。验收通过再发布 ONLINE；ONLINE 灰度仍是同环境稳定版/灰度版两版本。发布顺序按依赖：组件和能力 → Application → Skill → Workflow。版本不一致沿用现有明确提示重置策略，不偷偷热换卡片配置。

## 6. Workflow 与 Chat 共用

首版 Workflow：阅读理解 → 选题策划 → 内容成稿，三个必需节点，不跳过用户确认。创建项目/录入素材是启动准备，不额外算作 Skill 节点。

单独 Chat 的 Skill 可通过已授权能力访问用户已有项目，或根据明确请求创建项目。不得依赖必须存在的 Workflow runId 才能运行。后序节点使用前序最终结果及业务引用，需要细节时读取已有记录，不重执行业务操作。

刷新页面恢复当前运行状态和已保存 Surface；过程执行中展开，结束收起可查看，等待时显示“等待你确认”。内容业务服务不维护另一套节点 RUNNING/WAITING 状态。A2UI Action 的重复/过期请求由现有运行态校验加业务去重共同处理。

## 7. 边界与风险

- 不把素材中的指令当作系统指令；它是分析数据，不能授权工具或身份变更。
- 外部内容仅接收用户有权使用的资料；首版不自动转载或发布。
- 同一账号能访问自己的内容，不同账号互不可读写，包括导出和卡片 Action。
- 公网入口沿用账户会话和角色校验；RPC 身份来自服务可信上下文，不解析模型传入 cookie。
- 不默认把阅读材料写入长期记忆。知识库建设、全文检索、视频大文件存储单独评审。
- 自动发布是真实外部副作用，不因为首版“确认定稿”获得任何未来发布授权。
