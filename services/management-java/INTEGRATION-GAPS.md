# Management integration gaps

> Historical baseline dated 2026-09-21. For the approved manual-only scope and current implementation status, see [手填管理端说明](MANUAL-MODE.zh-CN.md).

This candidate contains the migrated management pages and Java domain services. Java 17 Maven source compilation and the frontend production build have passed. That is not evidence that a management application boots, that the HTTP endpoints exist, or that a page can edit and publish against the real database and Python Runtime. Subsequent source changes require a fresh build.

The inventory below comes from the current source and injection sites. It is not a claim that implementing seven interfaces completes the product. No application context boot, authenticated HTTP flow, migration deployment, or end-to-end publication acceptance has been established by this compilation result.

## Required ports without an implementation

These seven application interfaces have callers but no concrete implementation or `@Bean` definition in this candidate. They have no default-success behavior. With the current ordinary component scan, required constructor or field injection cannot be satisfied. A feature being unused in the browser does not make its eagerly constructed dependencies optional.

| Port | Required methods | Callers | Affected management surface |
| --- | --- | --- | --- |
| `ManagementIdentityProvider` | `namespace(): String`, `userId(): long` | `SkillWorkspaceRequestSession`, `DatabaseArtifactService` | Authenticated Skill workspace read/write and artifact access; no anonymous or client-supplied identity is permitted. |
| `AgentService` | `queryById(String, long): Agent`, `querySubAgent(long): List<Agent>` | `SkillFactoryChatRuntimeService` | Authoring chat agent selection and ownership validation across Skill, Ability and A2UI workbenches. |
| `SkillFactoryAiCodingModelClient` | `streamCall(LLMModelConfig, List<Message>, List<ToolCallback>): Flux<ChatResponse>` | `AiCodingReActEngine` | Authoring chat model output, tool proposals and streamed structured events. This is a compatibility port, not an implemented Python Runtime client. |
| `SkillFactoryRunControlService` | `registerCancellationToken`, `unregisterCancellationToken`, `markRunning`, `markCancelled`, `markFailed`, `markCompleted`, `queryStatus`, `requestCancel`, `isCancellationRequested` | `SkillFactoryChatRuntimeService`, `AgentBizTool`, `SkillFactoryMethodDispatcher` | Authoring run status, stop/cancel and terminal state. Status operations identify a run by session ID and invoke ID; token methods also receive an `AtomicBoolean`. `markRunning`, `queryStatus` and `requestCancel` return `SkillFactoryRunStatus`; the cancellation check returns boolean. |
| `SkillFactoryLabRuntimeQueryClient` | `queryRecentSkillRuns(QueryLabMessageListRequest)`, `querySkillRunDetail(QueryLabTraceDetailRequest)` | The recent-run and run-detail authoring tools | Real execution history, diagnostics and evidence available to the authoring assistant. The current port preserves structured response maps; the Python endpoint schema and error contract are not yet bound. |
| `SkillFactoryReleaseReadinessInspectionService` | `inspect(String workspaceId, Path workspacePath, String operator): ReleaseReadinessInspection` | The readiness inspection and release-evidence tools | Skill publication readiness and recorded gate evidence. Constants define existing evidence states; no implementation produces those states. |
| `RuntimeSkillPublicationPort` | `publish(SkillDraft, ReleaseArtifact, byte[], int version, String environment, String requestId): Receipt` | `SkillDatabasePublishService` | Skill PRT/ONLINE publication, including immutable definition and dependency installation in the target Runtime. The receipt contains asset key, environment, package digest, version ID and content digest. |

The following are not additional missing ports: `A2uiBuildIdGenerator` is supplied as a method reference by `A2uiApplicationManifestCompilerService`; authoring repository interfaces have database implementations; dependency, release, HTTP transport and model event parser interfaces have concrete source implementations. MyBatis mapper interfaces require framework assembly, covered below. `WorkspaceInitializer` is a callback supplied at its call site, not an unbound application bean.

## Java to Python boundary still needs implementation

The Runtime integration needs an authenticated transport, explicit endpoint configuration, request/response validation, error mapping, timeout and cancellation behavior, and event translation that preserves run, message, tool and observation identity. None is implied by declaring an interface or by adding local JSON DTOs.

The retained Java authoring engine contains execution orchestration from the migrated source. Its presence does not establish an accepted second Runtime. Before enabling authoring execution, integration must bind the approved Python Runtime boundary and decide which retained entry/event adapters are used. Adding an implementation that starts another Java agent loop would not resolve this boundary.

The model port currently exposes Spring AI message and tool types. The run-control port currently exposes local cancellation tokens. These are migration-facing contracts and require explicit translation to Python run/control semantics; they are not ready-made public Python API contracts. Likewise, the history query port must map to real Runtime records rather than return empty lists when no adapter is configured.

Publication must write and validate the actual Runtime definition and frozen dependencies, enforce environment isolation and request idempotency, and return a receipt grounded in the persisted state. Saving package bytes through `PostgresArtifactRepository` only stores a build artifact. It must not create a successful deployment or serving pointer by itself.

Readiness requires real workspace and Runtime evidence tied to the expected digest and rules. Neither compilation nor an absent diagnostic adapter may be represented as a passed gate.

## HTTP host and authentication are absent

`frontend/api.ts` requests these routes:

- `POST /api/management/v2/handler` for method-dispatched management operations.
- `POST /api/management/v2/bizrender` for rendering operations.
- `POST /api/management/v2/chat` for authoring SSE.
- `POST /api/management/v2/bindings/add` and `/bindings/remove` for bindings.

The candidate has dispatchers and service entry classes, but no HTTP controller/router definitions or standalone application bootstrap that expose these routes. The Java build produces compiled classes, not a configured running HTTP server. Generic handler responses must match the frontend's SSE envelope parsing; chat must preserve streaming, errors and terminal events. Zip/file transfer and cancellation also require the actual host behavior to be exercised.

The host must authenticate the request and derive a trusted namespace and signed 64-bit user ID. It must implement `ManagementIdentityProvider`, preserve request-scoped identity across asynchronous work, and enforce asset authorization without trusting display names, client headers or arbitrary request fields as credentials. User IDs remain exact decimal strings on the JSON boundary and are validated as `Long` internally. This document does not specify a default account or grant.

`SkillWorkspaceRequestSession` uses Spring's `request` scope and a scoped proxy. A real web request scope, request lifetime, transaction boundary and cleanup callback are required; an ordinary non-web Spring context is insufficient. A host must bind this session to the same authenticated request and transaction as metadata mutations.

## Database and MyBatis assembly are incomplete

There is a mapper scan configuration and migrated mapper/entity/repository source. There is no candidate configuration that supplies all of the following production beans and lifecycle wiring:

- A PostgreSQL `DataSource` with externally supplied credentials and an explicit target database.
- A Spring `ObjectMapper` bean for constructor injection. `JsonSupport.mapper()` is a static codec and does not itself register a bean.
- A MyBatis/MyBatis-Plus `SqlSessionFactory` or `SqlSessionTemplate`, appropriate SQL injection/configuration and transaction integration.
- A `PlatformTransactionManager` and enabled transaction advice that make the retained `@Transactional` boundaries effective.

`ManagementArtifactConfiguration` supplies only `PostgresArtifactRepository` and requires an existing `DataSource`. The workspace request session constructs its store from the host's `DataSource` and `ObjectMapper`. These adapters do not assemble the host or create its schema.

No versioned production SQL migrations are included in this candidate. JDBC verification helpers create limited test tables; those scripts/classes are excluded from the production build and are not a deployment schema. Current adapters refer to the shared `a2flow_management_drafts` and `a2flow_asset_versions` tables; the metadata mappings additionally refer to `skill_draft`, `skill_component_registry`, `workflow_definition`, `skill_capability_action_draft`, `skill_asset_release_state`, `entity_relation`, `skill_asset_principal`, `skill_factory_authoring_session`, `skill_factory_authoring_turn`, `skill_factory_authoring_event` and `agent_observation_event`. Migration ownership, columns, constraints, indexes, CAS behavior and compatibility with the existing database must be verified before startup.

The unused human-decision approval entity, mapper and repository were removed after verifying that no application callers remain. Do not recreate approval tables as a schema workaround.

Successful isolated PostgreSQL workspace/artifact checks establish those adapters' tested behavior only. They do not establish MyBatis CRUD, request-scoped transaction assembly, the management HTTP host or the original pages' real database interactions.

## Configuration and remaining acceptance

The Java configuration reader requires `A2FLOW_MANAGEMENT_CONFIG` (or system property `a2flow.management.config`) to identify a deployment-owned JSON file. Its sections are `agents`, `pages`, `prompts`, `permission`, `capabilityClusters` and `mountedSkillProtocolPrompt`. Agent, model, memory, workspace, change-guard and referenced prompt configuration must be provided for the invoked functionality. Missing permission configuration grants no administrators. Optional tool extensions and guide configuration retain disabled/empty behavior; they do not select a production environment.

`A2FLOW_ENVIRONMENT` (or system property `a2flow.environment`) must explicitly be `PRT` or `ONLINE`. Release source still uses the internal `PREPROD` enum, so boundary mapping to PRT must be explicit and verified. Endpoint configuration and environment names alone do not prove isolation or deployment.

Additional acceptance remains beyond the missing ports:

- Assemble and boot the full application graph without mock identities, placeholder-success adapters or hidden optionalization of required services.
- Apply reviewed schema changes and exercise real Skill, Ability, A2UI and Workflow create/read/update flows, with authorization and rollback/CAS failures included.
- Verify workspace edit, draft commit, immutable build and publication as separate lifecycle operations; validate the request-scoped file projection against PostgreSQL.
- Replace or reconcile process-local state such as `SessionService`'s in-memory map with the agreed persistence/recovery contract. That implementation is not proof of multi-instance chat recovery.
- Bind authoring event history, model/tool execution, cancellation and required A2UI user interactions to the real Python Runtime.
- Verify publication receipts and subsequent Runtime execution from each requested environment using the original management pages.

Source compilation is a completed prerequisite. Boot, authenticated CRUD, deployment, publication and end-to-end Runtime acceptance remain separate, unproven outcomes.
