# Management console MVP / 管理台首版

## Available scope / 已实现范围

One console connects the existing Skill, Ability, Application and Workflow management modules. Authenticated readers browse published lists and details. Administrators can edit existing assets as JSON drafts, save with revision checks, validate, and prepare an explicitly unpublished candidate.

统一管理台已接入 Skill、业务能力、Application 和 Workflow。已鉴权的普通用户可浏览已发布资产；管理员可编辑现有资产的 JSON 草稿、按修订号保存、校验，并生成明确标记为“未发布”的候选。

The first UI is a structured editor, not a visual graph or component designer. Standalone Component authoring, general new-asset creation, actual publication, version-history UI and rollback are not delivered by this slice. Preparing a candidate does not change published versions or serving selections.

首版为结构化编辑器，并非可视化流程或组件设计器。本批未交付独立 Component 编辑、通用新资产创建、正式发布、版本历史界面或回滚。生成发布候选不会修改发布版本或生效选择。

## Verification / 验证记录

The implementation at `9696bfc` was checked on 2026-09-16:

- Three frontend state tests, TypeScript/Vite build, and ten private-host tests passed.
- Intercepted browser fixtures covered all four kinds, administrator/read-only views, repeated category selection, preserving edits across navigation, pending-operation locking, revision conflicts and confirmed reload.
- A separate real Chromium session used the authenticated private Host and an isolated PostgreSQL database: three Skills, two abilities, three Applications and one Workflow loaded successfully. An administrator saved a same-content draft, validated it and prepared an unpublished candidate. Published lists remained unchanged.
- Unauthenticated access, client role spoofing and cross-origin writes were rejected. Desktop and narrow-screen checks found no horizontal overflow; the final browser run had no console or page errors.

`9696bfc` 已于 2026-09-16 完成上述前端状态测试、构建、Host 测试及浏览器验证。模拟接口测试与真实 PostgreSQL 联调分别执行；真实环境验证包括四类资产读取、管理员草稿保存/校验/候选生成，以及鉴权和跨站写入拦截。最终浏览器运行无控制台或页面错误。

This was a temporary, loopback-only verification window, not a permanent deployment. No model calls or external business operations were executed. The test database and temporary credentials are disposable; existing databases are outside this verification scope.

After verification, all ten immutable version rows and ten serving rows had the same aggregate digest as before. The temporary Host, database container, socket, credentials and tunnel were removed, and the source checkout remained clean.

本次为仅限本机访问的临时验证，不是常驻部署；没有模型调用或外部业务操作。测试库与临时凭据属于可清理资源，既有数据库不在验证范围内。

验证前后，10 条不可变版本记录及 10 条生效记录的汇总摘要完全一致。临时服务、数据库容器、socket、凭据和隧道均已清理，源码工作区保持干净。

See [private Host setup](../deploy/management/README.md) and [asset version decisions](adr/0005-asset-versions-and-rollback.md). The preview authentication is deliberately private and is not a production identity-provider implementation.

运行方式见以上链接。预览鉴权仅用于私有验证，不能替代生产身份系统。
