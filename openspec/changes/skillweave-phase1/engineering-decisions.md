# Phase 1 engineering decisions

Authority: main-brain's delegated routine engineering responsibility within SW-P1-20260907.2. These are scoped engineering decisions, not newly inferred user product approvals or runtime evidence.

## ENG-01: Python control-plane backend modules

Status: ACCEPTED for phase 1 module planning and subsequent reviewed implementation. Date: 2026-09-07.

- Skill, Ability, A2UI and Workflow registry backend domain modules use Python. Shared contracts/governance adapters may expose a thin Python package while retaining neutral schemas/examples as their contract source.
- This aligns backend dependency consumption with the already selected Python Runtime and avoids an additional online backend language on the constrained first host. Alternatives considered: separate TypeScript/Java backend stacks introduce additional packaging/process ownership without a demonstrated requirement at this stage. Revisit if concrete library or operational evidence changes the trade-off.
- Domains remain separate modules with their existing reserved source paths and owners. Shared language does not allow Runtime to import digital-employee business models or create Skill-specific business graphs.
- A module is not automatically an independently deployed resident service. Keep transport/process composition separable; this does not authorize starting four additional services.
- Frontend technology and the digital-employee BFF's final process/language choices are not changed by this M-backend decision.
- Prefer a small importable package under each existing reserved service directory. Owners submit exact package layout and required libraries; main-brain coordinates root project/lock files with contracts and Runtime. No concurrent edits to root dependency files or unreviewed full code-generation platform.
- Public APIs/library compatibility and dependency pins need evidence. Do not start multiple heavyweight installation jobs or alter host Python independently; PY-01's sole Runtime executor rule remains.
- Independent consumer inputs, fixtures and bounded library/package research may continue now. Dependent services still require an actually reviewed, named contract revision. Do not convert experimental schemas or adapter files into a second shared authority.

## Current review dispositions

- Skill alignment documents and independent examples, including corrections at commit `97ffc5e46f857eac6708b095ebe2280b8bb461fd`, passed the coordinator's bounded review. This is not package-validator or chat/Workflow runtime acceptance.
- Shared contract candidate needs safe instruction-relative resource mapping and one named Action-success policy shared across domains. A policy lookup on an exact currently resolved Ability version does not permit frozen-version continuation.
- Workflow default context must cover all relevant executed predecessor/ancestor final results, not only directly adjacent inputs. Full graph revision remains gated on correcting that discrepancy.

Review status changes require explicit delivery with a stable revision/commit. An integrated draft or passing synthetic shape check is not deployment or runtime readiness.
