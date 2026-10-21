# Contributing to A2Flow

Start with the [current architecture](docs/current-architecture.md) and [getting started](docs/getting-started.md). The current M frontend is `services/management-java/frontend`; `apps/management/web` is historical.

## A small, reviewable change

1. Open an issue describing the user-visible problem, reproduction and expected result. For an execution-semantics change, discuss stop/resume, authorization and migration impact first.
2. Create a branch in your own clone/worktree. Keep unrelated changes out of the patch.
3. Run `python3 scripts/check_repository.py` and `git diff --check`. Build a frontend if you change it; compile Java if you change its control plane. See the commands in the getting-started guide.
4. For runtime changes, include a targeted reproduction and evidence for the relevant failure boundary. Do not invoke a live business operation just to get a green check. Explain what was not verified.
5. Open a pull request with the problem, change, validation and material limitations. Update both home pages when changing capability claims.

CI runs repository checks, two current frontend builds, Java compilation and Compose syntax validation without model keys or production databases. The separate Python quality job covers two foundational typed modules; the core job additionally runs `scripts/check_python_dependency_types.py` for the explicit HTTP/composition scope. Neither is whole-repository type coverage. Builds do not replace end-to-end acceptance. The [core invariant probes](docs/core-probes.md) cover isolated PostgreSQL account/outbox and approval consumption, synthetic Chat/Workflow write confirmation, and Java archive guards without model keys or live business calls.

## Invariants

- User/environment context is server-authenticated. Never accept model-selected identity or broaden tool access to make a demonstration work.
- A required interaction resumes only its owning live task. Stop prevents new admissions but does not roll back business writes.
- Preserve `UNKNOWN` outcomes and saved history. No silent fallback or automatic business replay.
- Business idempotency belongs to the business service. Do not claim exactly-once from a platform request ID.
- Runtime core must not import B product or example-content domain modules.
- Use public Deep Agents/LangGraph extension points; do not patch vendor internals.

## Data, dependencies and attribution

Use synthetic data in issues and examples. Do not include secrets, session Cookies, private endpoints or production records. Report vulnerabilities through [SECURITY.md](SECURITY.md).

A2Flow-owned source is [MIT](LICENSE). Contributions must be yours to contribute or carry compatible documented permission. Preserve third-party copyright/license files and update [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) when vendoring code. Dependency changes should update the lock file and explain compatibility/security impact.

Be respectful and specific. Critique code and behavior rather than people. No formal support SLA is offered; prioritize bounded bug fixes and reproducible reports over broad rewrites.
