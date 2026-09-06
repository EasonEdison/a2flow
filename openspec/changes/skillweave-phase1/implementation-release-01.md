# Phase 1 implementation release 01

Approval record: `SW-P1-SUBSET-01`.
Authority: main-brain's delegated engineering responsibility under SW-P1-20260907.2 and ENG-01.
Status: APPROVED FOR THE BOUNDED SOURCE IMPLEMENTATION BELOW. Not full-contract approval or runtime readiness.
Date: 2026-09-07.

## Immutable review scope

Reviewed base content: `404bbcacc1ef176c273c9a90fc4ae91bfadc42fd`.
Final corrected schema snapshot: `a1cb44e88ce5bb603c62b4618804c78ae0d5585c`.
Schema SHA-256: `10fb8f2fb26529ba7850e981991bcb343037aa6defe7f22646e00f1cdf59fa3b`.
Schema source: `packages/contracts/schemas/contracts-bundle.schema.json`.

This record is an implementation-approval identifier, not a new wire protocol version. The wire field remains `SW-CONTRACTS-P1-CANDIDATE.1`. Only the following named definitions and their referenced primitive dependencies are approved for the scoped source work below; the rest of the bundle remains provisional:

- `trustedContext`, `trustedInvocationContext`, `invocationScope`;
- `useSkillRequest`, `skillKey`, `useSkillResult`, `useSkillContent`, `useSkillArtifact`;
- `authorizedMaterialHandle`, `skillAssetVersionRef`;
- `resultInterpretationPolicy`, `resultInterpretationPolicySet`;
- referenced `contractRevision` and `identifier` primitives.

Future changes to this subset require a scoped delta and consumer notification. A merge of unrelated candidate definitions does not silently change this approval.

Main-brain inspected the exact dependency closure, complete focused checker, and final identifier/skillKey CR/LF correction plus its three negative examples. Independent final verification: 57/57 synthetic contract checks passed, schema hash matched, diff whitespace passed and source was included in main. These checks are shape/semantic-fixture evidence only; trusted provenance, side effects and runtime persistence remain separate gates.

## Work released now

### Contracts owner

Implement a thin importable Python package at `packages/contracts/src/skillweave_contracts/`, limited to the reviewed subset: model/serialization adaptation, schema loading and reusable structural/semantic validation. Reuse the neutral schema and existing synthetic cases; do not build a generator framework, resolver, scheduler, result interpreter or database adapter here.

Reject extra fields and implicit coercion where the neutral contract rejects them. Preserve duplicate-policy/default-resolution and unique-resource-path checks. A model-only Skill request cannot carry server identity/environment/version arguments. Mapping names to Python classes must be explicit, not a new external contract.

### Skill registry owner

Start `services/skill-registry/src/skill_registry/` as an importable domain module. First slice: bounded read-only package-entry/resource validation, catalog/material ports and mapping of verified instruction/resources plus trusted resolution evidence into the approved use_skill result shape.

Use immutable descriptors and bytes/streams supplied by a trusted adapter; enforce finite entry/byte/path limits, logical-path uniqueness, declared size/digest agreement and strict UTF-8 for text while retaining opaque binary assets. Compute evidence from actual bytes; synthetic placeholder digests must not become implementation defaults. Compatibility metadata never grants Tool or script authorization.

Do not parse YAML with a homegrown parser. Frontmatter-library selection is a separate small dependency decision and does not block descriptor/byte validation. No generic archive extraction, shell/script execution, server filesystem locator supplied by a model, production fallback or real database connection in this slice. A module constructor/port does not itself prove trusted-context provenance or version admission.

### Capability registry owner

Start `services/capability-registry/src/capability_registry/` as an importable domain module. First slice: authored Ability definition validation and named success-policy publication metadata using the approved common policy set. Preserve nonempty unique policy names, a resolvable explicit default and the consumer model/server-input separation. Keep backend credentials as ports/references, never model-visible values.

The domain may validate its own authored payload and adapter-operation binding metadata; it must not implement a second policy evaluator, invoke business APIs, implement business retries/idempotency or assume PostgreSQL/admission already exists. Runtime owns the one evaluator and Tool execution adapter.

### Runtime owner

The already authorized SDK experiment may replace provisional local Tool-boundary DTOs with this named subset and the shared thin package when available. Continue the fixed-source use_skill admission/provider-serialization checks, then A2UI interruption and independent parallel progression. Do not pause independent framework probes merely because another Registry is unfinished.

This release does not approve the full graph/control/event/Action wire contract or establish persistence, multi-instance safety, mandatory use_skill enforcement, artifact isolation, business correctness or runtime readiness. Explicit interaction must remain LangGraph-backed; no second scheduler or per-Skill business subgraph is authorized.

## Packaging and delivery limits

- Python 3.11 is the first validation target. Pydantic 2.13.5 is already present in the Runtime experiment environment and may be reused for thin models; using it is not permission to coerce data or to install a separate dependency stack. Standard-library-only domain code is preferred where sufficient.
- Each owner may add its own source/tests/README under the listed reserved paths. Root manifest/lock files remain main-brain-owned. No concurrent package installation or new resident process is authorized by source-module approval. Exact packaging/build metadata can be coordinated after the first importable source slice; it must not block source implementation or silently become a second lock.
- Use existing synthetic examples and focused checks proportional to the small implementation. Test doubles stay at ports/repositories, not as hidden production fallback. Verify imports and contract compatibility, then inspect the exact diff and sensitive-data boundary.
- Commit in each existing exclusive server worktree/branch, merge fresh origin/main before delivery, push the worker branch and automatically integrate through its exclusive integration worktree. No company/local Git mutation, force push or shared writable checkout.
- Return a stable source SHA, exact touched paths and fresh verification evidence. Keep implementation, schema tests, SDK probes, PostgreSQL integration and real product/runtime proof distinct.

## Still outside this release

Full A2UI/Host protocol and digital-employee BFF language/implementation; graph/control/event admission; production databases/services/public routes; keys/model-provider setup; live business writes; knowledge-base expansion; generic Skill recovery; business reconciliation/rollback. These are not implicitly authorized by this subset.
