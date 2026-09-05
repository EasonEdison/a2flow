# Change Proposal: M 侧 Skill 注册平台首个设计切片

> 状态：**PROPOSED**
> Runtime 准出：**NO READY**
> 审批者：main-brain / CTO
> 本文描述设计候选，不代表协议已冻结、实现已完成或功能可用。

## Why

M 侧需要一个边界清晰的 Skill 注册平台，向作者提供目录、注册、元数据编辑、版本化包引用和依赖校验，并向后续 Workflow Composer 与通用 Runtime 提供稳定、不可变、可审计的发布引用。若把可编辑元数据、包存储、依赖解析和运行执行混在一起，将很难保证发布可复现，也会把 Runtime 错误耦合到 M 侧数据库。

## First Slice

本 change 只设计以下能力：

1. 创建和查询 Skill 目录项。
2. 以乐观并发方式编辑目录元数据。
3. 为一个 Skill 创建带 SemVer 的版本候选，绑定内容寻址的包描述符。
4. 校验 Agent Skills 基础结构，以及已声明的 Capability/Workflow 依赖。
5. 发布前把版本约束解析为精确、不可变的依赖锁；发布动作复用公共发布协议。
6. 目录查询仅暴露已发布版本，并能返回可供消费者解析的发布引用。

本轮不实现代码、数据库、接口或部署。

## Explicit Non-goals

- 不做 AI Coding/Prompt 编辑器、在线文件树或通用低代码 IDE。
- 不接收、解压、重打包或管理任意 ZIP；注册平台只接收公共协议定义的包描述符。
- 不执行 `SKILL.md`、`scripts/` 或包内任意代码。
- 不设计任意 Skill-to-Skill 传递依赖、依赖求解器或插件市场。
- 不拥有 Workflow 图、Capability 契约、制品仓库、Runtime 运行状态或 B 侧展示。
- 不在协议未裁决前绑定具体 Runtime 语言、AG-UI/A2UI 版本或单一部署形态。

## Options and Recommendation

### 包引用

| 候选 | 优点 | 主要代价 | 结论 |
| --- | --- | --- | --- |
| Git URL + commit | 易审查、MVP 简单 | 分发、鉴权、media type 与完整性语义需另补 | 保留为导入来源，不作为发布主引用 |
| 平台自管 ZIP/对象存储路径 | 可完全控制 | 会扩展成上传、压缩、清理和安全扫描平台；路径可变 | 首片拒绝 |
| 公共 `ArtifactDescriptor`，以 digest 寻址并兼容 OCI descriptor | 不可变、可校验、可替换后端；与共享发布协议对齐 | 需 contracts 任务冻结字段与制品后端 | **推荐** |

推荐注册平台只持久化公共 `ArtifactDescriptor`（至少包括 `mediaType`、`digest`、`size` 和受控 locator），由公共发布协议/制品端口负责上传、下载与鉴权。OCI descriptor 将 media type、digest 和 size 作为内容描述核心，且 OCI manifest 明确允许承载非容器制品，适合作为兼容目标，而非要求首片自建 OCI Registry。

### 版本与依赖

| 候选 | 结论 |
| --- | --- |
| 全部依赖只能手填精确发布引用 | 确定性强，但作者体验差 |
| Runtime 每次按 SemVer range 动态解析 | 同一 Skill Release 可能随时间执行出不同结果，拒绝 |
| 草稿声明 SemVer range，校验/发布时锁定精确 release + digest | **推荐**：兼顾作者体验与可复现执行 |

SemVer 2.0.0 要求已发布版本内容不可修改；本方案据此将发布快照设计为不可变，并把后续变更发布为新版本。

### 部署边界

逻辑上保持独立 Skill Registry 模块与端口。为匹配首个纵向切片和小型主机，建议四个 M 侧能力先作为模块化单体中的独立模块部署；是否拆成独立服务由 main-brain 统一裁决，本文不冻结。

## Public References

- [Agent Skills Specification](https://agentskills.io/specification)：`SKILL.md`、YAML frontmatter、目录名/name 一致性及可选资源目录。
- [OCI Content Descriptor](https://specs.opencontainers.org/image-spec/descriptor/)：media type、digest、size 与内容寻址/校验。
- [OCI Image Manifest - Artifact Usage](https://specs.opencontainers.org/image-spec/manifest/)：非容器制品可使用 manifest 与 artifact type。
- [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)：版本优先级和已发布内容不可变。

## Cross-domain Dependencies

| 依赖方 | 本域输入 | 本域输出 | 所有权 |
| --- | --- | --- | --- |
| oss-platform-contracts | `AssetIdentity`、`ArtifactDescriptor`、`ReleaseRef`、幂等/授权/撤销语义 | Skill 消费者对字段和状态的要求 | contracts 最终冻结公共发布协议 |
| oss-capability-registry | Capability 可解析/可发布状态与精确 release ref | 版本候选中的 capability requirements | capability registry 拥有契约和发布状态 |
| oss-workflow-composer | Workflow 校验结果与精确 release ref | `SkillRevisionRef` 和绑定要求 | workflow composer 拥有图与图发布 |
| oss-agent-workflow-runtime | 无草稿访问；仅消费已发布、已锁定 Skill release | `PublishedSkillRef` 与 dependency lock | Runtime 拥有执行，不得读取本域数据库 |

为避免 Skill 与 Workflow 发布循环，建议先产生不可变 `SkillRevisionRef`，Workflow 以该 revision 编排；最终 Skill Release 再绑定精确 `WorkflowReleaseRef`。该两阶段边界需 main-brain 与 workflow/contracts 任务共同裁决。

## Success Criteria

- 规范明确可编辑目录、不可变版本、校验报告和发布引用的区别。
- 发布结果只包含精确依赖与 digest，不允许运行时动态解析。
- 失败、重试、并发、多实例和失效边界有可验证定义。
- 5–8 个验收场景覆盖成功、冲突、非法包、缺失依赖、完整性和幂等发布。
- 所有运行态门禁维持 `NO READY`，直到实现与回归证据齐备。

## Decisions Requested from main-brain

1. 公共发布协议是否采用 OCI-compatible descriptor 作为规范形状，以及 locator 是否允许 registry URL 之外的后端。
2. 是否批准“两阶段 SkillRevision → WorkflowRelease → SkillRelease”以消除循环依赖。
3. MVP 是否只允许 Capability/Workflow 依赖，暂不支持 Skill-to-Skill 依赖；以及四个 M 模块是否先同一部署单元。
