# Core invariant probes

The [public workflow](../.github/workflows/core-probes.yml) adds bounded runtime
checks to the existing syntax and build jobs. It needs no model key, installation
configuration or production data. It does not rerun a live business operation or
replace [full self-host acceptance](../openspec/changes/portfolio-selfhost/readiness.md).

| Probe | Real boundary checked | Deliberately synthetic |
| --- | --- | --- |
| Python route composition | Actual generic/attended/realchat B and Runtime assembly, immutable route order and OpenAPI wire contracts | External database/network/model dependencies replaced; no listener |
| Chat durable delivery | PostgreSQL transactional request/continuation inbox, concurrent dispatch, fresh worker recovery, completed projection repair and parameter-based HTTP endpoints | Scripted runner with explicit execution facts; no model keys or business effects |
| Chat state convergence | PostgreSQL terminal-message/dispatch atomicity under trigger failures, source/client concurrency, durable card-task binding failure recovery, exact live-vs-snapshot projection equality, strict complete-result validation, and incompatible-schema rejection without mutation | Saved synthetic public events; no external model or business calls |
| Chat dispatch wake | PostgreSQL commit/rollback admission, lost-hint process exit, cross-process locking, bounded wake/slot scheduling, centralized task settlement, retry-persistence fault backoff, waiter cleanup and default idle reconciliation measurement | Scripted native facts and card action, synthetic business receipts; no external model/business calls |
| Chat native recovery | Actual Deep Agents execution completion, validated final snapshot, advisory lock and abrupt worker exit | Scripted model, no external tools or live operations |
| Account guard | PostgreSQL cross-process admission, shared M/B limits, trusted proxy parsing, password recovery and session revocation | Account and ASGI requests; no public HTTP server |
| Runtime outbox | PostgreSQL transaction failure, duplicate/ack recovery, fresh-process delivery, native LangGraph waiting checkpoint recovery | Reference transport/failure injection; no Redis/external sender or business dispatch |
| Chat/Workflow write approval | Confirmation and continuation contracts through the dedicated Python probes | Fake RPC/model replies and in-memory state, no database or network access |
| Python capability approval | Actual Python executor admission and PostgreSQL consumption, read-only role with minimal append privilege, concurrent and fresh-process replay rejection, unknown outcome not retried | Recording/fault-injected business transport; no public RPC/mTLS server |
| A2UI write preflight | A2UI preflight and confirmed dispatch through the actual Python executor/guard | Synthetic transport and in-memory receipts; no network |
| Java capability approval | Management execution admission plus durable PostgreSQL receipt consumption, aliases and concurrent consumption | Local fake business transport |
| Management context startup | Production Spring composition root, dependency injection, real PostgreSQL pool and loopback gRPC lifecycle start/close | Empty isolated database, temporary JSON configuration; no HTTP request or business dispatch |
| Package restore | Archive admission, extraction limits and workspace preservation | Small generated archives and temporary workspaces |

The Python/PostgreSQL and Java suites are independent jobs. Failure is nonzero, never a
skipped pass. Probe assertions remain enabled. The runner requires every selected
probe to emit its success result and checks that PostgreSQL probe schemas are gone.

## Python/PostgreSQL suite

Requirements: Python 3.11+, Docker with a local Linux engine and about 1.5 GiB
available RAM for the disposable containers. The dependency image uses the
existing runtime/scheduler locks; its Dockerfile reconciles the recorded psycopg
patch version to the scheduler's 3.3.6, adds the existing model SDK lock and the
self-host `jsonschema==4.26.0` pin without changing the pinned gRPC/runtime
dependencies. Building needs package-registry access;
the probes themselves run in a network namespace with no external interface.

From the repository root:

```sh
docker build -f openspec/changes/portfolio-runtime-outbox/Dockerfile.probe \
  -t a2flow-core-probes:local .
docker pull postgres:16.6-bookworm
python3 scripts/run_core_probes.py --run-id local-core-check
```

The runner creates its own PostgreSQL container with a random password, seven empty
databases and RAM-backed storage. No port is published. The seven database probes
join only that container's network namespace; the Chat/Workflow/A2UI probes run in
separate `network none` namespaces. Source is mounted read-only; private DSN files are
owner-only, outside the checkout, and removed on exit. No installation DSN is
accepted. The whole disposable container is removed even if a probe fails.
The Python executor probe creates and removes its dedicated synthetic role and
table. The role retains `default_transaction_read_only=on`; only the consumption
connection opts into writes, with `INSERT, SELECT` and no update/delete privilege.
Use `--python-probe capability-approval` for that focused local reproduction.
CI always selects all eleven Python probes; the report identifies narrowed runs.

For Colima or another explicitly selected local Docker context, build/pull with
`docker --context CONTEXT ...`, then pass `--docker-context CONTEXT` to the runner.
The checkout/export and scratch directory must be shared with the VM. For example,
with an existing `/tmp/colima-a2flow-selfhost` share, run from a source export there
and add `--scratch-dir /tmp/colima-a2flow-selfhost` and
`--source-root /tmp/colima-a2flow-selfhost/EXPORT_DIRECTORY`. The source override
must resolve to the same checkout as this runner; it only preserves the path
shared with the VM when macOS resolves `/tmp` to `/private/tmp`. The runner does not start a VM
or change the default Docker context.

Each probe has a 300-second local default deadline; `--probe-timeout` can set
1–600 seconds. The Python CI job uses 180 seconds per probe.
Timeout/termination kills the child process group and cleans the labeled
containers. If the host is killed before cleanup, remove only the resources from
the known run, using the same Docker context:

```sh
python3 scripts/run_core_probes.py --cleanup --run-id local-core-check
```

Use a distinct run ID for concurrent invocations. The CI adds run ID and attempt
and always executes this cleanup separately; hosted runner disposal is the last
boundary for an uncatchable host kill. Do not use a broad Docker prune.

## Java suite

Use JDK 17, Docker and the existing management Maven build:

```sh
mvn --batch-mode --no-transfer-progress -f services/management-java/pom.xml \
  -DskipTests compile dependency:copy-dependencies
docker pull postgres:16.6-bookworm
docker pull eclipse-temurin:17-jre-jammy
python3 scripts/run_core_probes.py --suite java --probe-timeout 60
```

Only the three explicit probe mains are compiled into a temporary directory and run
with assertions enabled. This does not execute the full unit suite or start the
management application. The approval probe uses a public JRE container and
loopback fake transport, sharing its isolated PostgreSQL namespace for the
durable consumption checks. The runner requires `postgres: true` in its result,
then verifies schema cleanup. The startup probe registers the same
`ManualManagementConfiguration` in the same `AnnotationConfigWebApplicationContext`
type as the production host, without replacing beans. It checks actual guard/store
registration, database connection and gRPC lifecycle shutdown. A temporary hosts
file resolves the isolated container's own hostname without DNS access.
It publishes no ports. The archive probe runs in
the local JDK with disposable files. All three must be present in the selected source
revision; a missing probe is a failure.
For a focused local reproduction, add `--java-probe package-restore` or
`--java-probe capability-approval` or `--java-probe management-context`.
The report records this narrowed selection; CI always runs all three, and a
focused pass is not a pass of the whole Java gate.
Use the same `--docker-context`, `--source-root` and `--scratch-dir` options for a
VM-backed engine. Keep the Maven outputs inside the exported source tree so the
JRE container can read `target/classes` and `target/dependency`.

## Reports and limits

Reports default to `artifacts/core-probes/postgres.json` and `java.json`; use
`--report-dir` to write outside the checkout. They include the run ID, individual
probe results and cleanup status. Failed commands retain bounded stderr with the
generated database password redacted; no private DSN file or raw container log is
uploaded. GitHub keeps these two synthetic JSON artifacts for seven days.

These probes establish particular invariants, not public HTTPS correctness,
real-model orchestration quality, general exactly-once business behavior, restore
readiness or load capacity. Local execution of the same commands and a successful
GitHub workflow run are separate evidence.

The core job also runs `python scripts/check_python_dependency_types.py` in its
pinned probe image. It directly checks 31 files, including the neutral Chat state/result contracts and transaction-local turn registry, alongside the expanded HTTP, persistence and production
composition scope with real SDK types, without ignoring missing imports. Only
legacy imported function calls are allowed in the explicitly listed migration
boundaries; new HTTP and Runtime transport modules remain strict. Dynamic SQL
values and extensible JSON payloads do not replace service dependency types.

Use `--python-probe chat-state-convergence` for the 26 current-schema PostgreSQL fault-window and production projection tests. This is not a compatibility migration: obsolete schemas fail explicitly without being rewritten or cleared. Runtime completion recovery reads a verified final snapshot and never calls the live runner. The transport event journal remains mutable within its explicitly fenced generation; it is not an immutable event-sourcing log.

## Chat scheduling measurement scope

Select `--python-probe chat-dispatch-wake` for the new isolated group. Its JSON report includes the observed candidate-reconciliation count over more than 30 seconds with the default 30-second interval, and local transaction-return-to-scripted-runner-start samples. These are measurements of the disposable PostgreSQL fixture, not public provider latency or a production benchmark. The signal and process fixtures also test lost hints, coalescing, stop cleanup and contention fairness.
