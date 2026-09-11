# AF-MVP-08: database-seeded, browser-visible MVP

Date: 2026-09-11. Coordinator: main-brain.
Accepted source baseline: b50d5a274be699fef7e0e569b6cdfeee6dd87f40 (AF07).
Status: user-approved priority and MVP scope; implementation starts in the bounded ownership below. Exact cross-owner interfaces must be checked against existing source before consumers freeze them. Source, seed execution, live integration and deployed browser readiness are separate results.

## Decision and scope

The user approved writing Skill and related definitions directly to PostgreSQL to run the smallest real MVP, without building the four M-side authoring platforms first. This supersedes the earlier engine-only pause for the three narrowly resumed workstreams below. M platform editors, CRUD/publication dashboards and unrelated domains remain paused. Their long-term product scope is deferred, not deleted.

Deliver one independently authored activity-planning demonstration:

1. User opens the digital-employee page and explicitly starts the predefined Workflow from its sidebar with a short requirement.
2. A real DeepSeek-backed Skill uses registered Tools and instruction assets to prepare candidate activity plans. Its natural-language steps are not compiled into a fixed business subgraph.
3. An interactive A2UI choice/confirmation card waits for a node-bound user action. Only configured successful completion and the existing Finalizer allow progression.
4. A subsequent Skill uses the confirmed result to prepare promotional copy; show the final output and preserved history.

The example is platform-owned demo data, not an external business integration. Any demo ability must return real local computation or stored demo records and be labeled accordingly; never represent mock results as external business success. No external publishing, payment, message sending or company data is required.

## Assets and import

- Seed Skill instructions/resources/bindings, the minimal capability definitions, component catalog/Application definitions including interaction and Action success policy, and the Workflow definition. Model selection remains deepseek-v4-flash; credentials never belong in an asset document.
- Store definitions in PostgreSQL and resolve them through trusted configuration adapters. Runtime use still enters via use_skill, execute_ability and render_application. Do not read hardcoded fixture dictionaries as a silent substitute for failed DB resolution.
- Preserve separate PRT and ONLINE asset databases. Trusted environment chooses the connection, not model/browser parameters. PRT resolves current only; ONLINE resolves stable or at most one gray version by userId, never PRT. A first demo needs only one serving version but must not erase these boundaries.
- Reuse existing shared validation and Skill CatalogPort/MaterialPort where applicable. Missing Application/Workflow adapters are explicit implementation work, not assumed shipped M services. Do not replace accepted shared contracts wholesale.
- Supply a versioned, reviewable seed bundle and a bounded import command with validation/dry-run. Resolve the exact destination and asset namespace before writing. Same identifiers plus same content are no-ops; conflicting existing content fails without overwrite. Validate cross-references and digests, commit a coherent environment-local bundle in a short transaction, and read it back for verification. No transaction spans model/API calls; no destructive reset or broad SQL replacement.
- Initialization is an operator operation, not a public authoring endpoint and not an automatically repeated migration on each HTTP request. Schema migration and demo seed are distinct, inspectable steps. No cross-database distributed transaction is required; report each environment independently.
- Record effective versions at runtime; mismatches on continuation/Action ingress require explicit reset, not silent version switching or preservation of old executable configuration.

## Minimal browser product

- Existing approved conversation layout and Workflow sidebar, real node states, stream display, saved read-only details and valid A2UI controls.
- Running process expanded; terminal process auto-collapses with truthful status. Model/Tool return and capture_end never mean Workflow success. Waiting confirmation retains the configured input/card.
- Browser refresh reconstructs the original run, results, pending cards and committed progress, then reconnects observation. It must not start another execution. Run discovery, trusted identity bootstrap and snapshot/history joins are required integration work.
- Preserve stop and fresh restart semantics. Repeated controls retain platform request deduplication; no generic Skill retries, business rollback or hidden model fallback.
- D2 node supplemental input remains accepted but later than this first visible slice. Do not show a working-looking composer without a backend. Ordinary chat must never implicitly control a waiting Workflow.
- No four M-side editors, knowledge-base/memory settings expansion, arbitrary uploaded script execution, multi-provider support or cross-datacenter failover in this slice. Existing architectural boundaries remain.

## Ownership and delivery

| Owner | Exclusive new work | Reuse / boundaries |
| --- | --- | --- |
| oss-skill-registry | packages/asset-store/, examples/activity-planning/, own OpenSpec evidence | Thin multi-asset import/read adapters only; no M UI. Coordinate port signatures with Runtime before freezing. Existing skill-registry edits only if necessary and disclosed. |
| oss-agent-workflow-runtime | services/agent-workflow-runtime/, experiments/runtime-phase1/ MVP verification, deploy/mvp/ | Host lifespan, real model/PG wiring, Tool and graph adapters, trusted execution/read transport; consume asset package, no scenario logic in core. Own proposed Compose/dependency delta and exact run commands. |
| oss-digital-employee | apps/digital-employee/, own OpenSpec evidence | Minimal frontend and typed Runtime client; no duplicate scheduler or invented success states. Relevant frontend skills apply. |
| main-brain | release/contract decisions, root instructions, integration and private coordination | Verify adoption, review exact changes, integrate only accepted candidates and synchronize GitHub. |

Use existing server-owned worktrees, fetch and merge origin/main, preserve dirty state. Owners may implement independently inside their reserved paths once their concrete interface mapping is reported; main-brain resolves shared changes promptly. Do not treat this as a blanket wait for all platform contracts. Main integration remains after fixed-candidate review. No new user-mediated kickoff is needed.

Initial handoff must report adopted baseline, exact reusable symbols, missing seams, proposed API examples and affected paths. Send conflicts directly to main-brain; do not ask the user to relay messages. Messages and plans are not implementation evidence.

## Verification and release gates

1. Import validation, repeated import/no overwrite, digest readback, missing binding rejection, PRT/ONLINE and userId isolation.
2. Actual database-backed configuration -> use_skill -> real model -> authorized capability/Application Tools -> persisted interaction -> configured Action -> legal continuation -> final result.
3. Active run discoverable before long POST returns; refresh during running and waiting restores the same run, no new model/ability dispatch from reads. Reconnect uses committed cursors and labels incomplete observation.
4. Wrong-user access, stale card/version, duplicate Action, stop, waiting-not-complete and normal error cases. No raw secrets/internal provider payloads reach browser.
5. One reviewed live flash command with bounded calls/tokens/time, retries disabled and host-only credential resolution; record real provider evidence distinctly from mock transport tests. No automatic provider fallback.
6. Review exact PostgreSQL/Compose resource targets, dependencies and port exposure before one coordinated executor runs them. User approval covers MVP implementation and intended deployment, not arbitrary public access, unrelated service changes or destructive cleanup. Prefer loopback/tunnel for initial private preview; public routing/security changes require their exact scope.
7. Deploy from clean accepted origin/main, verify actual browser interaction and refresh, report a usable access method plus known limitations. Do not call the MVP ready because source tests passed.

## Scheduling

Asset adapter and frontend preparation can run concurrently with Runtime host wiring. Finish a shared integration contract before connecting them; do not wait for any M platform. Retire the previous unsupported 2-3 day estimate. Give a new estimate only after these owners report actual gaps, dependencies and a runnable critical path. Priority is one visible complete journey rather than additional infrastructure-only slices.
