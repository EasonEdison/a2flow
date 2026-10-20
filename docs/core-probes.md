# Core invariant probes

The [public workflow](../.github/workflows/core-probes.yml) adds bounded runtime
checks to the existing syntax and build jobs. It needs no model key, installation
configuration or production data. It does not rerun a live business operation or
replace [full self-host acceptance](../openspec/changes/portfolio-selfhost/readiness.md).

| Probe | Real boundary checked | Deliberately synthetic |
| --- | --- | --- |
| Account guard | PostgreSQL cross-process admission, shared M/B limits, trusted proxy parsing, password recovery and session revocation | Account and ASGI requests; no public HTTP server |
| Runtime outbox | PostgreSQL transaction failure, duplicate/ack recovery, fresh-process delivery, native LangGraph waiting checkpoint recovery | Reference transport/failure injection; no Redis/external sender or business dispatch |
| Capability approval | Management execution admission and protected dispatch, using the dedicated Java probe | Local fake business transport and in-memory receipts |
| Package restore | Archive admission, extraction limits and workspace preservation | Small generated archives and temporary workspaces |

The PostgreSQL and Java suites are independent jobs. Failure is nonzero, never a
skipped pass. Probe assertions remain enabled. The runner requires every selected
probe to emit its success result and checks that PostgreSQL probe schemas are gone.

## PostgreSQL suite

Requirements: Python 3.11+, Docker with a local Linux engine and about 1.5 GiB
available RAM for the disposable containers. The dependency image uses the
existing runtime/scheduler locks; its Dockerfile reconciles the recorded psycopg
patch version to the scheduler's 3.3.6. Building needs package-registry access;
the probes themselves run in a network namespace with no external interface.

From the repository root:

```sh
docker build -f openspec/changes/portfolio-runtime-outbox/Dockerfile.probe \
  -t a2flow-core-probes:local .
docker pull postgres:16.6-bookworm
python3 scripts/run_core_probes.py --run-id local-core-check
```

The runner creates its own PostgreSQL container with a random password, two empty
databases and RAM-backed storage. No port is published. Each probe joins only that
container's network namespace. Source is mounted read-only; private DSN files are
owner-only, outside the checkout, and removed on exit. No installation DSN is
accepted. The whole disposable container is removed even if a probe fails.

For Colima or another explicitly selected local Docker context, build/pull with
`docker --context CONTEXT ...`, then pass `--docker-context CONTEXT` to the runner.
The checkout/export and scratch directory must be shared with the VM. For example,
with an existing `/tmp/colima-a2flow-selfhost` share, run from a source export there
and add `--scratch-dir /tmp/colima-a2flow-selfhost` and
`--source-root /tmp/colima-a2flow-selfhost/EXPORT_DIRECTORY`. The source override
must resolve to the same checkout as this runner; it only preserves the path
shared with the VM when macOS resolves `/tmp` to `/private/tmp`. The runner does not start a VM
or change the default Docker context.

Each probe has a 300-second deadline; `--probe-timeout` can set 1–600 seconds.
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

Use JDK 17 and the existing management Maven build:

```sh
mvn --batch-mode --no-transfer-progress -f services/management-java/pom.xml \
  -DskipTests compile dependency:copy-dependencies
python3 scripts/run_core_probes.py --suite java --probe-timeout 60
```

Only the two explicit probe mains are compiled into a temporary directory and run
with assertions enabled. This does not execute the full unit suite or start the
management application. The approval probe uses a loopback fake transport; the
archive probe uses disposable files. Both must be present in the selected source
revision; a missing probe is a failure.
For a focused local reproduction, add `--java-probe package-restore` or
`--java-probe capability-approval`. The report records this narrowed selection;
CI always runs both, and a focused pass is not a pass of the whole Java gate.

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
