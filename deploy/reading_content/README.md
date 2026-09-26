# 阅读到创作 PRT authoring

本目录只包含场景资产和通过 M 正式 HTTP authoring/release 接口执行的工具。它不直写发布表、不创建管理 DDL、不读取 Cookie/token，也不发布 ONLINE。

## 真实契约

- RPC：`a2flow.content.v1.ContentService` 的 12 个 unary 方法一一对应 `content.*` 能力；所有能力共用由仓库 `content.proto` 编译出的 FileDescriptorSet，但各自固定 `methodName`、输入字段和嵌套 request mapping。
- 客户端：本场景能力发布合同只支持 `PC` variant，dry-run 也固定使用可信客户端 `PC`，由 M 把 `PC` 写入 RPC `TrustedContext.client`；不依赖 `COMMON` fallback。
- 组件：复用 B 已注册的 official basic catalog 组件。阅读确认使用 `ChoicePicker(multipleSelection)`；选题在重复候选卡内用按钮提交标量 `topicId`，避免把单选数组错误映射到 protobuf string；稿件编辑使用 `TextField(longText)` 和已真实注册的 `Markdown`。
- 下载：唯一新增依赖是 B 注册的 `TextDownload`。它只接收 `label/filename/mediaType/content` 和标准 `Checkable` 字段，使用内联 Blob，不接受 URL。
- 关系：Skill 通过 `SKILL_BINDINGS_REPLACE` 写入能力和 Application 关系；可选 Workflow 使用既有 v2 graph，并由 `WORKFLOW_DRAFT_UPDATE` 重新校验三个 Skill 的专员关系。

稿件 DataModel 将 `draftTitle/draftMarkdown` 与 `savedTitle/savedMarkdown` 分离。保存成功后 adapter 才更新 `savedArtifactId/savedArtifactRevision`，同时原子清空旧 export；确认、导出和下载均用 official `equals/required` checks 阻断未保存内容，下载还核对 export 的 artifact ID/revision 与当前保存身份一致。

创建项目的 `outputFormat` 是内容形态枚举，只允许 `ARTICLE` 或 `SPOKEN_SCRIPT`，与稿件导出格式不是同一概念；当前验收样例固定使用 `ARTICLE`。`SaveArtifact` 的模型输入保持扁平，但 request mapping 会按 `kind` 分别写入 `body.readingBrief`、`body.topicPlan` 或 `body.manuscript`，一次请求只能出现一个 protobuf oneof 分支。

## 浏览器执行（真实 PRT）

将本目录作为 M 同源静态内容提供，管理员登录后打开 `import.html`。页面不会自动执行，只有用户勾选审核确认并点击“创建并发布阅读创作示例到 PRT”后才调用 `/api/management/v2/handler`。

点击“加载本项目 Content RPC 契约”会显式读取同目录的 `content-descriptor.txt`，校验 base64 后填入文本框，但不会开始 authoring 或发布。也可以手工粘贴 base64 FileDescriptorSet 文本，或选择含同一内容的文本文件（两者同时提供时粘贴文本优先），并填写固定 `targetKey`、M 当前专员 ID。页面用当前 HttpOnly 同源会话，代码无法读取或输出该 Cookie。失败不会自动重放发布请求；再次点击时按稳定 actionCode/appCode/skillCode 查找并复用已有资产，若发现重复身份或不同 digest 的活动变更会停止。

`content-descriptor.txt` 是部署静态资源，不含凭据，不得手写。当前文件由本仓库 `packages/rpc-contracts/proto/a2flow/content/v1/content.proto` 在集成提交 `4dde853` 上生成，并通过 `grpc_tools.protoc --include_imports` 纳入 `services/management-java/proto/a2flow/capability/v1/capability.proto`；原始 FileDescriptorSet 的 SHA-256 为 `eb261f17724397d5bf935f15283bbfdbe08cf69f54458b475280d3ceea8917b7`。协议变更时必须从同一待部署提交重新生成 base64 文本，并让离线测试核对 12 个方法后再随本目录部署。

空库首次导入应保留“同步 M 内置锁定的 Google A2UI Official Basic Catalog”勾选。该操作调用无客户端 schema 参数的管理员固定方法，由 M 从随二进制发布的资源读取 [Google A2UI v0.9.1 Basic Catalog](https://github.com/a2ui-project/a2ui/blob/420c6183c400e4b84fe3f9e084906725062a6d56/specification/v0_9_1/catalogs/basic/catalog.json)：协议版本 `v0.9.1`、source commit `420c6183c400e4b84fe3f9e084906725062a6d56`、catalog SHA-256 `8cc94d0a482e67048f9fc989964ca5da56fe42f531d919315a508989fb22e13e`。服务端会再次核对原文件、rules 和协议文档摘要；页面不上传、不拼装、不简化官方 schema。`Markdown` 与 `TextDownload` 仍由本项目作为独立扩展注册，绝不标记为 Official。

`digital-employee-functions.json` 是从本仓库 B 端 `apps/digital-employee/web/src/catalogs/digital-employee-functions.json` 精确复制的公开项目合同：14 个函数 `$ref` 到上述 locked official Catalog，仅 `equals` 来自已锁定的 `@a2ui/web_core` `0.11.0` `EqualsImplementation`。浏览器只在用户点击发布按钮后同源读取该文件；M 将合同随项目 Catalog 发布并据此校验 FunctionCall，不接收或执行任意脚本。

当前正式 M 的受控分类只有 `general/general` 和专员 `101`，因此本工具的 Capability 与 Skill 都使用该现有分类，不修改全局配置。若首次 `CAPABILITY_DRAFT_CREATE` 已成功而随后的 SAVE 失败，重试会按唯一 `nameCn` 复用 actionCode 仍为空的初始 draft；同名候选超过一个时停止，避免重复身份。

当前 M SPA 没有可恢复的资产直达 URL，结果区会提供管理台入口和可复制的真实资产 Key，不伪造深链；同时可以下载不含凭据的 PRT manifest。浏览器在 12 项 dry-run 全部成功后把无凭据 checkpoint 存入同源 `localStorage`；若后续 Catalog/Application/Skill 发布中断，再次点击会先核对 12 个 draft identity/revision 后从发布阶段继续，避免为重试重复创建能力资产或改写已验证 digest。完成后 checkpoint 会被移除，只保留便于复用 workflowCode 的 manifest。

## 隔离 CLI

Node CLI 只允许 loopback 且强制 `M_FRESH_TEST_DB=1`，用于隔离 PG/M/content-service 联调：

```sh
M_REVIEW_CONFIRM=reading-content-prt-v1 \
M_FRESH_TEST_DB=1 \
M_ORIGIN=http://127.0.0.1:18080 \
M_SESSION_COOKIE='a2flow_management_session=...' \
RPC_DESCRIPTOR_FILE=/secure/path/content-descriptor.base64 \
RPC_TARGET_KEY=content-service \
M_SPECIALIST_IDS=101 \
B_WEB_DIR=/path/to/apps/digital-employee/web \
M_BOOTSTRAP_BASIC_CATALOG=1 \
OUTPUT_FILE=/secure/path/reading-content-prt-manifest.json \
node deploy/reading_content/author-prt.mjs
```

`M_INCLUDE_WORKFLOW=1` 时还必须传 `M_SPECIALIST_CODE`；中断后重试 Workflow 应传上次 manifest 的 `M_EXISTING_WORKFLOW_CODE`，否则后端会生成新的 Workflow identity。三个独立 Chat Skill/Application 不依赖 Workflow。

离线检查不会发 HTTP：

```sh
node deploy/reading_content/author-prt.mjs --check
node deploy/reading_content/test-assets.mjs
```

## ONLINE 后续门禁

本批明确只发布公网 PRT。当前能力的 `inputExampleJson` 进入发布 source digest，而 Get/Save/Confirm/Export dry-run 需要引用环境内真实生成的 UUID。如果 PRT 与 ONLINE 使用隔离内容库，同一个不可变 digest 无法同时携带两套环境 fixture identity；修改 ONLINE 样例又会使 PRT build digest 过期。因此工具不做跨环境 fallback，也不使用 force 绕过门禁。后续需由控制面提供不进入业务快照的环境独立 dry-run fixture，或其他经评审的正式契约，再启用 ONLINE。
