# AF-MVP-08 asset mapping and gaps

Status: implemented source candidate for main-brain review, 2026-09-11. This document does not
publish AF-MVP-08 or approve DB writes. Base origin/main:
b50d5a274be699fef7e0e569b6cdfeee6dd87f40; worker merge:
a557c0092361917dda0cca4de6cf9b908e04f122.

## Scope and ownership

The current assignment releases this document and two original Skill texts.
Candidate implementation ownership is packages/asset-store/; examples belong
under examples/activity-planning/. Final implementation release belongs to
main-brain. No M management platform, shared schema edits, dependency install,
DB connection, migration execution, resident process or deployment in this batch.
The preserved pause checkpoint remains part of this thread's history.

## Existing interfaces and minimum mapping

Paths below are repository-relative evidence, not new external contracts.

| Consumer | Existing interface / evidence | Proposed store mapping and gap |
| --- | --- | --- |
| Skill catalog | services/skill-registry/src/skill_registry/ports.py: CatalogPort.list_skills(trusted_context) | Return permitted environment-local metadata only; descriptor response type is not frozen. Never include instruction bytes or credentials in discovery. |
| Skill material | same file: MaterialPort.load_skill(skill_key, trusted_context) -> SkillMaterial | Read instruction_entry and resource_entries bytes plus required_tool_names and TrustedResolutionEvidence. Continue through registry use_skill; never return raw material directly to model. |
| Runtime Skill | experiments/runtime-phase1/runtime_phase1/skill_registry_adapter.py: SkillRegistryResolver.__call__(skill_key, shared context) | Reuse the existing shared-to-Registry context conversion and UseSkillResult.to_mapping. Production location/wiring is Runtime-owned. |
| Ability definition | services/capability-registry/src/capability_registry/validation.py and models.py | Persist validated authored definition and operation reference; reuse shared policy validator and trusted operation catalog. No executable Python or credential value stored in asset payload. |
| Ability execution | experiments/runtime-phase1/runtime_phase1/ability_probe.py: AbilityExecutionPort | Current result requires synthetic=True; unsuitable for real execution. Runtime must name the MVP executor adapter/result before store wiring; asset reader does not invoke business APIs. |
| Application Action | services/agent-workflow-runtime/src/agent_workflow_runtime/ports.py: ConfigurationPort.versions/action | Resolve current full version closure and ActionConfig using the same trusted environment/userId. Callable validators are backend bindings, never JSON-loaded code. |
| Application rendering | experiments/runtime-phase1/runtime_phase1/a2ui_probe.py: ApplicationResolver(key, context) | Existing dict contains application, contentDigest, resolvedVersion, recordedVersions. Probe discards data and chooses actionPolicies[0]; real card data and action selection require Runtime owner review. |
| Workflow entry | services/agent-workflow-runtime/src/agent_workflow_runtime/service.py: resolve_entry(owner, definition_key) | Existing callback returns entry ID only. Stored definition -> graph compilation/execution_session is Runtime-owned and not yet a frozen store interface. |

Use shared TrustedContext/TrustedInvocationContext, UseSkillRequest,
UseSkillResult, asset/version reference and result policy primitives unchanged.
Local store records are persistence details, not a new shared wire revision.
No separate generic resolver endpoint exposed to the model.

## Proposed minimum persisted information

One immutable asset-version collection, one bounded material-entry collection
and one serving-state collection are sufficient; exact tables/columns await
AF-MVP-08. Store only an explicit namespace, asset kind, logical key, asset ID,
version ID, authored payload, digest, material descriptors/bytes and serving
selection references. Do not duplicate runtime run/interaction/checkpoint state.

Candidate namespace: a2flow-mvp-activity-planning. This exact value must be
confirmed by main-brain before any import. Namespace is configured by the
trusted host/import command, never supplied by model arguments. No default,
wildcard or cross-namespace search. PRT and ONLINE require separate PostgreSQL
databases and separately bound adapters; an environment column alone is not
sufficient isolation. Reject a connection whose configured environment binding
does not match trusted context. No database names or credentials are invented here.

PRT resolves one current PRT version. ONLINE resolves at most one stable and
one gray version from ONLINE only. An optional finite explicit trusted-userId
membership list is the smallest proposed MVP gray rule, subject to approval;
no percentage hash algorithm is implied. Selection is derived only from trusted
userId. Missing/ambiguous serving state or missing selected version fails closed;
do not fall back to another environment, namespace, version or local file.
Ended gray state has one serving version. Selection and version read must share
a consistent snapshot. ConfigurationPort version guards still apply on resume.

Proposed digest rule, requiring release confirmation: SHA-256 over exact UTF-8
SKILL.md bytes per instruction entry; existing validator recomputes entry size
and digest. Artifact digest must also bind all entries and compatibility metadata,
not use a placeholder or only SKILL.md. Define one deterministic, documented JSON
encoding of authored metadata plus sorted logical-path/size/digest descriptors
before implementation; sorting must not alter semantic list order. The importer
and readback must use the same encoding. JSONB textual output is not an original
byte representation. Preserve source bytes or the canonical encoded payload.

## Import workflow and invariants

1. Require explicit environment, exact namespace and reviewed bundle path.
   Bound files/entries/bytes using existing ResourceLimits. Reject duplicates,
   unsafe logical paths, unknown kinds/fields and dangling references before write.
2. Dry-run parses and validates the complete bundle and computes actual digests;
   read-only DB comparison may classify insert/no-op/conflict once DB access is
   released. Dry-run performs no DDL, DML or serving-state update.
3. Compare immutable namespace/kind/key/version identity and full content.
   Same bytes/metadata/serving state => NO_CHANGE with no timestamps or rows
   rewritten. Changed content under the same identity => conflict, no overwrite.
4. Validate serving-state changes separately. This importer cannot silently
   repoint existing current/stable/gray slots. Existing differing state is a
   conflict unless a later explicit publication operation is approved.
5. Apply one all-or-nothing transaction per namespace/environment bundle.
   Enforce unique identities and recheck concurrent inserts/serving cardinality;
   a dry-run is not a write reservation. No upsert-overwrite or partial apply.
6. Read back exact inserted/existing asset bytes and dependencies, recompute and
   compare digests before commit and verify committed content after commit.
   A failed post-commit readback reports verification failure with potentially
   committed outcome, never claims rollback or automatically repeats writes.
7. Report only namespace, environment, asset identities, digest and status.
   No credential values, connection strings or actual userId lists in output.

The future verification matrix includes dry-run no writes; repeated no-op;
changed existing version conflict; mixed bundle atomicity; concurrent duplicate
import; missing namespace/environment; PRT/ONLINE physical isolation; gray
membership and two-version limit; stale version closure rejection; corrupt
readback; missing references; and actual Tool-based two-Skill execution.
These are PLANNED, not passing test results.

## Scenario and decisions needed for release

Original content lives in examples/activity-planning/activity-plan/SKILL.md and
activity-copy/SKILL.md. First Skill prepares options and requests confirmation
through a configured Application. Second Skill writes copy only from the
confirmed outcome. They contain instructions, not a fixed internal graph.
Workflow sequencing and wait/resume belong to Runtime; ordinary chat does not
complete an interaction. Text must remain useful in other authorized contexts.

Before coding: main-brain confirms namespace, digest encoding, asset manifest
shape, gray membership rule and named Runtime resolver/executor/graph mapping.
Do not store provisional Application/Workflow schemas merely to fill bundle rows.
A choice-confirmation operation and any required Ability must have an explicit
backend-owned result policy and completion flag. Unknown tool keys remain
unbound rather than invented. Source docs can be reviewed now; runtime NO READY.

## Implemented AF-MVP-08 source decision

Main-brain approved the fixed namespace, deterministic JSON encoding, explicit
trusted-user gray list, and the two sequential Skill workflow. The source
candidate now implements those choices under packages/asset-store/ and
examples/activity-planning/.

The importer validates all five asset kinds, per-version SHA-256 digests,
closed fields, dependency closure, immutable identity/no-overwrite semantics,
and the Application's declared component and pinned Ability release. The reader
uses one environment-local repository snapshot, chooses only PRT current or
ONLINE stable/explicit trusted-user gray, and rejects a selected Ability version
that differs from an Application action's pinned release.

The package deliberately defers PostgreSQL connection and setup until a caller
explicitly invokes those commands. This candidate has only offline tests using
an SQL protocol double: they exercise validation, no-op/conflict/rollback,
physical environment guard, digest readback, Registry use_skill byte
round-trip, and gray selection. It does not constitute live PostgreSQL,
Runtime/Tool, browser, deployment, or production readiness evidence.
