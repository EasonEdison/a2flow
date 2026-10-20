# A2Flow contributor instructions

These are stable code and delivery rules. Current implementation is documented in [docs/current-architecture.md](docs/current-architecture.md); historic plans and dated readiness records do not override a current task's explicit scope.

## Responsibilities

- Java owns M-side asset authoring, validation, compilation and publication. Python owns shared account login, B-side product APIs, Agent/Workflow execution and business services.
- Current M frontend: `services/management-java/frontend`; current B frontend: `apps/digital-employee/web`. Do not update a historical frontend and claim the current product changed.
- Runtime remains business-independent. Product copy, content-domain models and B product persistence must not be imported into the generic engine.
- Deep Agents owns the agent loop; LangGraph provides graph/checkpoint/interrupt execution. Use public SDK extension points, not vendor patches or a second competing graph scheduler.
- PostgreSQL is the supported relational engine. Do not introduce implicit SQLite/MySQL fallbacks.

## Execution invariants

- Resolve assets using trusted environment/userId and current effective publication. PRT and ONLINE remain separate. Model arguments cannot choose arbitrary identities or environments.
- Skills enter through `use_skill`; abilities and UI rendering use authorized tools. Entry authentication does not remove resource ownership and execution-state checks.
- Runtime asset updates do not require old cards to RESET merely because revisions differ. Preserve publication history, management draft CAS, request idempotency, execution claims and authorization.
- Missing input belongs to a specific task/node. A valid temporary-interaction submission resumes that task automatically; unrelated chat does not control a workflow.
- Stop prevents new admissions and continuation. Preserve real late outcomes of already dispatched business operations; do not undo successful writes or convert stopped runs to success.
- Restart is fresh execution. Control-request deduplication is not business exactly-once. Business idempotency/retries belong to the business API; no generic automatic retry or silent success/fallback.
- Viewed notifications, completed handling tasks and resolved business anomalies are distinct facts. A saved draft does not establish business resolution.

## Changes and validation

- Work in a task-owned branch/worktree from a current target branch. Inspect status before editing; preserve unrelated changes. Never stash/reset/clean someone else's work or force-push shared history.
- Implement the authorized scope. Record material execution-contract changes and alternatives before coding; ordinary local fixes do not require a new product decision.
- Follow local types and conventions. Keep fixed protocol structures typed; parse structured data structurally. Do not use blanket ignores to hide errors.
- Read [CONTRIBUTING.md](CONTRIBUTING.md) and run the relevant documented checks plus `git diff --check`. State omitted checks. Do not add tests that merely duplicate implementation.
- Separate source completion, deployment and actual execution evidence. Build success is not runtime readiness; historical evidence is not a fresh acceptance run.
- Deploy only a reviewed, integrated, clean source revision when authorized. Preserve recoverable configuration and actual service launchers; never silently swap the real-chat entry for a fixture host.
- Keep secrets, production data and private material out of code, logs, issues and documentation. Inspect exact outgoing files before publication and preserve third-party notices.

## Documentation

Update both README languages for capability claims. Link current architecture and scoped evidence, label synthetic previews, and retain historical evidence without presenting old plans as current status. Track unfinished changes in a task-specific checkpoint; do not overwrite another task's cursor.
