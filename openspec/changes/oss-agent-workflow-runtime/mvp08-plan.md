# AF-MVP-08 Runtime integration plan

2026-09-11. Started from b50d5a274be699fef7e0e569b6cdfeee6dd87f40, then consumed the
accepted asset owner release 6ac3f56f59baf24c204cd5c52436089b633abff8 from origin/main.
Adopted AF-MVP-08 coordinator release in full. The owned source candidate and offline
evidence below are implemented; PostgreSQL, model, credential, listener and deployment
commands remain separately bounded and were not run.

## What exists / what is missing

All paths below are repository-relative and verified at the adopted source.

| Boundary | Existing implementation | Required MVP work |
| --- | --- | --- |
| Host | services/agent-workflow-runtime/src/agent_workflow_runtime/service.py: RuntimeService, ExecutionSession; assembly.py: build_engine | Real execution_session context manager, shared lifespan/resource ownership, asset adapters and authenticated ASGI factory are absent. |
| Model | model_factory.py: DeepSeekModelFactory; model_config.py: parse_deepseek_configuration | Host configuration resolver and host-only SecretStr resolver; flash only, max_retries=0. No key read in this planning step. |
| Skill | services/skill-registry/src/skill_registry/ports.py: MaterialPort/CatalogPort; use_skill.py: use_skill | Consume asset owner's PG MaterialPort; promote experiment SkillRegistryResolver/use_skill Tool bridge into Runtime without changing shared types. Registry context differs from shared context, so retain explicit translation. |
| Ability | services/capability-registry/src/capability_registry/: authored-definition validation; experiments/runtime-phase1/runtime_phase1/ability_probe.py | SyntheticAbilityResult is explicitly synthetic and unusable as a real result. Build a Runtime-local real Tool adapter over trusted asset resolution and an allowlisted local operation map. |
| Application | experiments/runtime-phase1/runtime_phase1/a2ui_probe.py: closed model args, ActionService registration/native interrupt loop | This probe deletes data and uses first action policy; no durable display snapshot. Retain control mechanics, add validated material/data/policies and saved display-only or interactive card projection. |
| Action | actions.py: ActionService; ports.py: ConfigurationPort/ExecutorPort; langgraph_adapter.py: LangGraphContinuation | PG current-version closure + policy-to-ActionConfig resolver; real demo executor; reconstruct same compiled graph with same lifecycle/saver on an authorized Action. |
| Workflow | native_control.py: guarded_node/guarded_router/RunGraphBinding; experimental native branch/PG probes | No production definition loader/compiler. Composer JSON is PROVISIONAL_CONSUMER_REQUIREMENT, not a released executable schema. Compile an explicitly agreed minimal definition to native LangGraph. |
| Persistence | postgres_lifecycle.py: PostgresRunRepository; postgres.py: PostgresInteractionRepository; postgres_projection.py; postgres_progress.py | Compose these with PostgresSaver and asset databases. Existing PG probes are verification fixtures, not a production host bootstrap. |
| Browser restore | AF05 snapshot + AF07 capture catalog/history/SSE | No owner Run list, identity bootstrap, final-output/card body endpoint, or authoritative complete per-node view. Never infer node success from RETURNED/capture_end. |

Existing filenames in the table without a prefix are under
services/agent-workflow-runtime/src/agent_workflow_runtime/.

## Smallest Python integration contract

Sent directly to asset owner for exact import/signature confirmation; not a new shared schema.

- Existing MaterialPort.load_skill(skill_key, registry_trusted_context) -> SkillMaterial.
  CatalogPort.list_skills remains asset-owned discovery.
- resolve_workflow(definition_key, owner) -> validated definition + effective version closure.
- resolve_application(application_key, invocation_context) -> application, resolvedVersion,
  contentDigest, recordedVersions; reuse the existing resolver shape where valid.
- resolve_ability(ability_key, invocation_context) -> validated definition, operation reference,
  version evidence and input/output contracts; resolution itself has no business effect.
- versions(owner, definition_key) -> tuple[(assetType:assetId, versionId)] for the complete
  current dependency closure. Record on start; mismatch on Action/continuation requires reset.
- Demo operation implementation and scenario data stay in examples/activity-planning/,
  injected through a trusted operation map. Runtime dispatches by authorized operation_ref;
  no arbitrary import path, URL, Python code, caller-selected owner or automatic retry.

Asset owner owns packages/asset-store/ and examples/activity-planning/. Trusted environment
selects separate PRT/ONLINE asset DB connections; no cross-environment fallback. A single
serving demo version does not remove future stable/gray/userId resolution boundaries.

## Minimal Workflow mapping implemented for the source candidate

First release: two sequential generic SKILL nodes (activity planning, promotional copy).
The first Agent reads its Skill through use_skill, chooses allowed ability/Application Tools,
waits for configured confirmation, and completes only under existing Action/Finalizer evidence.
The second consumes confirmed predecessor final results. It does not consume every raw token
or force the first Skill to produce platform routing fields.

Compile nodes/edges from the validated seeded definition, never compile SKILL.md prose into
business steps. Stable outer node identities and native checkpoint namespaces survive authorized
Action reconstruction; each activation/continuation gets a new AF07 display segment.
Other graph forms must explicitly reject until their native mapping is implemented/released;
this is the accepted first-demo subset, not removal of approved branching/parallel product scope.

## HTTP mapping and refresh

Reuse all current control and progress APIs listed in mvp08-http-examples.md.
Start/Action POSTs are synchronous, not 202 job submission. The caller owns a durable
controlRequestId; while POST is pending, independent GET control discovers the allocated run.
A missing receipt is not authority to issue a new control or replay an uncertain operation.

Implemented additive Runtime-local reads under the bounded MVP08 view contract:
- GET /runtime/session: authenticated user/environment bootstrap, never an identity setter.
- GET /runtime/runs?limit=20&after=opaque: bounded trusted-owner run discovery.
- GET /runtime/runs/{runId}/view: committed node lifecycle view, safe final outputs and saved
  cards with typed render data/action descriptors. Keep native checkpoint/provider payloads private.

Refresh reconstructs an existing run using reads, then reconnects AF07 observation cursors.
It never invokes graph/model/ability/render/Action, never sends Command(resume), and never
resolves newer assets to pretend old cards were originally rendered from them.
Saved card display material is historical evidence, not permission to execute old configuration:
Action entry revalidates current versions and disables/rejects stale or stopped interactions.
Final result persistence and definitive node terminal state must come from execution/Finalizer,
not from the observation writer. Missing/unconfirmed observations remain visibly unconfirmed.

D2 process expansion/collapse and read-only terminal details apply. Supplemental input is
deferred: no fake send control or ordinary chat steering of a waiting Workflow.

## Owned paths and executable order

Runtime owns new implementation under services/agent-workflow-runtime/src/agent_workflow_runtime/:
mvp_host.py (lifespan/authenticated factory), asset_adapters.py (port bridging), mvp_tools.py
(real Tools), workflow_loader.py (native compilation), ui_projection.py (saved read model),
plus relevant tests. Final filenames can remain smaller if existing modules suffice.
Runtime owns deploy/mvp/ Compose/command candidates and experimental MVP verification only;
root integration/packaging/shared-schema changes need main ownership coordination.

1. Freeze the small asset return shapes + demo operation map with asset owner; UI view shape
   and private-preview authentication with UI/main. No four M services required.
2. Implement Tool adapters + graph compiler + PG-backed host, with injected ports and offline
   boundary tests while asset implementation proceeds. No synthetic fallback.
3. Implement persisted card/final/node views, owner discovery and session bootstrap; connect UI.
4. Review exact migrations/import targets + model/PG budgets with main, then one coordinated
   live window proves asset -> Skill -> actual flash -> local ability -> card -> Action -> result.
5. Deploy only clean accepted origin/main through reviewed Compose, then browser refresh proof.

Resolved source dependencies and remaining live decisions, without user relaying:
- Asset owner: accepted importable package, Workflow subset, complete effective version closure,
  Application binding/policy and demo operation schemas at 6ac3f56.
- UI/main: final small view contract and authentication mechanism; recommend private
  loopback/tunnel preview with authenticated host session, not public client-supplied userId.
- Main: exact PG schemas/resources/DSNs, credential read authority, live call/token/time caps,
  Compose service/port/resource review. Do not start any of them from this document.

## Implemented source candidate

- RuntimeAssets consumes the accepted AssetReader interfaces and freezes the complete Workflow
  version closure on each Run. Skill calls are restricted to the current compiled node; Ability
  and Application calls are restricted to the Run closure and trusted operation map.
- The strict compiler accepts exactly two sequential generic Skill nodes. Each child remains a
  native graph inside a RunnableSequence, so the A2UI interrupt remains visible to the parent
  checkpointer. A deterministic idempotent NODE fact spans interruption and authorized resume.
- Every node gets a trusted fixed context covering model callbacks, Tool admission, Finalizer and
  AF07 progress capture. The caller cannot select or replace that node context.
- render_application validates the accepted Application profile, saves the historical display
  JSON atomically with the Interaction binding, registers the Action, interrupts natively, and
  returns only after the saved successful Action result is consumed on resume.
- The view projection uses only committed Run, view and Interaction documents. Refresh and list
  routes do not construct a graph, model or Tool. Cards are ordered deterministically, duplicate
  interaction identities fail closed, and operability is recomputed from saved lifecycle facts.
- MvpRuntimeHost owns the PG repositories, PostgresSaver, progress writer, per-execution models
  and Action continuation assembly. Invalid Workflow inputs are rejected before Run allocation,
  entry resolution, model construction or graph assembly.
- deploy/mvp is source-only private-host wiring: environment-bound owner, DeepSeek flash only,
  max_retries=0 through the existing factory, explicit operation allowlist and optional same-origin
  static directory. Import does not perform DDL, read credentials, open a listener or call a model.

Accepted seeded profile facts:

- ChoicePicker id is selection; root children are prompt, selection, confirm.
- Button label is 确认这个方案; prompt and option-label maxLength are 2000.
- plan requires execute_ability and render_application from the Skill asset; Runtime additionally
  requires use_skill. copy requires only Runtime-added use_skill.

Offline verification after final code changes:

- 94 affected Runtime unit/integration-style tests PASS in 4.711s, including actual seeded
  plan -> native interrupt -> saved Action -> resume -> copy completion using scripted models.
- compileall for Runtime and deploy/mvp PASS; canonical wire JSON parse PASS.
- deployment module import with dummy non-routable PG configuration PASS and performs no connection.

Evidence boundary: no PostgreSQL schema/setup, asset seeding, DeepSeek credential read or request,
AF07 live listener, HTTP socket, Compose apply, server deployment or browser regression was run.
This is a worker source candidate, not READY or deployed runtime evidence.
