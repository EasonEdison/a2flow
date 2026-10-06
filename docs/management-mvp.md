# Management console MVP / 管理台首版

## Historical record / 历史记录

This page records the September 2026 Python management MVP. Its CRUD host and publication bridge were retired in the October 6 Java management migration. The historical `apps/management` frontend remains in source, but is not the current management deployment. Test counts and browser results below apply only to their recorded commits.

本文保留 2026 年 9 月 Python 管理台的历史验收；其 CRUD 服务和发布桥已在 10 月 6 日迁移中退役。当前管理端为 Java，发布直接写入环境资产库；账号登录仍可由独立 Python 服务提供。`apps/management` 历史前端保留，但不是当前部署入口。下文验证数量和浏览器结果只对应记载的旧提交，不能作为新链路验收。

Current configuration: [Java management guide](../services/management-java/MANUAL-MODE.zh-CN.md). Runtime and migration boundaries: [Chat execution guide](../services/management-java/RPC-CHAT.zh-CN.md).

## Publication UI update / 发布界面更新

AF12-B (UI candidate `8d1710c`, reviewed integration `ab32dbb`) connects retained-version browsing, explicitly confirmed publication and configuration rollback. Ordinary users remain read-only. Changing a draft or publication target invalidates its prepared candidate. Pending writes lock navigation and editing. Successful writes refresh history, detail and the asset list; a later refresh failure is distinguished from a failed write. Conflicts require manual refresh and review, never automatic retry.

AF12-B 已接入保留版本列表、明确确认后的正式发布与配置回滚。普通用户保持只读；修改草稿或发布目标会废弃已准备候选；写入期间锁定导航和编辑。写入成功后刷新版本、详情和目录；后续刷新失败会与写入失败区分。并发冲突必须手动刷新并复核，不自动重试。

Four frontend state tests and the TypeScript/Vite build passed. A real Chrome browser with intercepted API fixtures covered four asset categories, PRT/ONLINE administrator flows, read-only access, cancel confirmation without writes, target invalidation, pending locks, retained unsaved edits, explicit rollback and stale-CAS conflict recovery. Page identity/content, absence of framework overlays, console health, screenshots and interactions passed at 1440×1000 and 390×844; no horizontal overflow or unexpected console/page errors were observed. The expected 409 conflict was exercised deliberately.

4 项前端状态测试及 TypeScript/Vite 构建通过。真实 Chrome 使用模拟接口验证四类目录、PRT/ONLINE 管理员操作、只读权限、取消确认不写入、目标变更失效、等待锁定、保留未保存草稿、显式回滚与 CAS 冲突恢复。1440×1000 和 390×844 下完成页面身份、非空内容、无框架错误层、控制台、截图及交互检查；无横向溢出或非预期控制台/页面错误。409 冲突为主动覆盖的预期情况。

The Browser plugin was unavailable, so existing Playwright and system Chrome were used without installing dependencies. These new UI flows have fixture-browser proof and separate real PostgreSQL backend proof, not a combined real-database browser run. There is no permanent deployed URL. General new-asset creation, visual designers, coordinated multi-asset publication and a chronological operator audit log remain outside this delivery.

Browser 插件不可用，本次使用现有 Playwright 与系统 Chrome，未安装新依赖。新增操作已分别完成模拟接口浏览器验证、真实 PostgreSQL 后端验证，但尚未进行二者结合的端到端浏览器联调，也没有常驻部署地址。通用新资产创建、可视化设计器、多资产联动发布、按时间记录的操作审计仍未交付。

## Publication backend update / 发布后端更新

AF12 (`e120f6c`) adds explicit single-asset publication, retained-version listing and configuration rollback APIs. Candidates remain unpublished until an authorized explicit request. Changes use a serving digest precondition and a namespace transaction lock; stale requests fail. ONLINE stable selection clears gray routing; incompatible selected Application/Ability bindings are rejected. Coordinated multi-asset publication remains deferred.

AF12 已新增单资产正式发布、历史版本列表与配置回滚接口。候选只有经管理员明确发布才生效；生效摘要与 namespace 事务锁保护并发修改，过期请求失败。ONLINE 发布正式版本会清除灰度；不兼容的 Application/业务能力版本绑定会被拒绝。多资产联动发布暂未实现。

Independent checks passed 19 asset-store tests and 18 management tests (one optional PostgreSQL test skipped). Separate real PostgreSQL acceptance covered racing publishers, immutable history, rollback, ONLINE gray/promotion, physical PRT isolation, and HTTP read/admin/stale-write behavior. The disposable database container and socket directory were removed; no models, business operations or existing databases were used. Frontend integration is tracked separately; these backend tests are not browser or deployment evidence.

独立验证通过 19 项资产测试和 18 项管理测试（另有 1 项可选 PostgreSQL 测试跳过）。另行执行的真实 PostgreSQL 验证覆盖并发发布、历史保留、回滚、灰度切换、PRT 分库隔离及 HTTP 权限/冲突。临时数据库容器和 socket 目录已清理，未使用模型、业务接口或既有数据库。前端集成单独记录，后端测试不代表浏览器或部署验证。

## AF11 baseline scope / AF11 已实现基线

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

The old private Python Host setup was removed with the retired service. See the current Java management guide above and the historical [asset version decisions](adr/0005-asset-versions-and-rollback.md). The old preview authentication was limited to private verification.

当前运行方式见页首 Java 管理端链接。旧预览鉴权仅用于私有验证。
