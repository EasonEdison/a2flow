# Regression evidence

Baseline: `main@5c907ee4054a83a2ea9f6cf831659dd1312de20b`. Validation uses a
source export on macOS and the existing task-owned `colima-a2flow-selfhost`
context; no local Git checkout, ECS builds or production operations.

## Completed

- Built the existing public `portfolio-runtime-outbox/Dockerfile.probe` using its
  cached dependency layers. Result:
  `sha256:73a46dd6009587a7fe62535d65860cace46b4719ba9aee0bc89dbca54a0b9c78`.
  This is a cached build, not a new cold-package-download proof.
- Ran the unified PostgreSQL runner against a new PostgreSQL 16.6 container with
  no network interface, no published port and RAM-backed data. Account guard
  passed: 32 cross-process attempts, 7 admissions, 25 limits, shared M/B quotas,
  trusted proxy boundary, synthetic password recovery and old-session revocation.
- Outbox probe passed all 15 existing checks, including deferred transaction
  rejection, ack failure, duplicate reference, fresh-process delivery and native
  waiting checkpoint recovery. Business calls and external sends were both zero.
- Independently checked both probe databases for leftover custom schemas: zero.
  Checked labeled containers and private temporary directories after execution:
  none remained.
- A controlled 1-second probe deadline returned nonzero with `deadline exceeded`;
  its container/private-file cleanup completed. This is failure-path verification,
  not a successful probe run.
- A deliberately pre-existing disposable container with the same run ID caused
  rejection before database startup. That container remained untouched until an
  explicit `--cleanup` for that exact run ID; no labeled resources remained.
- Workflow YAML parsed; both event path lists include services, packages, deploy,
  contracts, scripts and the Docker build-context ignore file. Both jobs have
  explicit deadlines and all external actions use full commit SHAs. This is a
  local structural check, not the GitHub workflow engine.
- Package probe source and its three production classes were exported from
  `9d84cbc6144ca165ab28df0a980992097e608727`, compiled using JDK 17 against the
  previous verified management classes/dependencies, and run through the same
  runner. Result: 107 checks, zero external calls, PASS. This focused run does not
  establish the complete Java suite or a fresh whole-module Maven build.
- Subsequently overlaid approval sources from
  `da2ff11f65b56fd67b3d1cb83116a50245582d99` onto the same independent export and
  ran the workflow's standard Maven `compile dependency:copy-dependencies` with
  JDK 17. All 609 Java sources compiled, including regenerated outputs from the
  three canonical proto files. Both probes then passed in the default `all`
  selection: approval 32 checks with five loopback fake RPC calls and
  `postgres=false`; archive 107 checks with zero external calls. This Java gate
  does not claim to test the approval store against real PostgreSQL.
- Applied the delivered V003 SQL twice through the actual self-host
  `bootstrap.apply_file` function in another empty isolated PostgreSQL database.
  It produced one schema-history row and the empty approval-consumption table.
  The dedicated container and private configuration were removed. This targeted
  check does not repeat the complete self-host setup sequence.
- Dependency-free repository checks passed: 354 Python files, 101 local entry-doc
  links and the current direct-import/manifests checks. `git diff --check` passed.

Two initial local runs exposed Colima's `/tmp` versus `/private/tmp` bind-mount
boundary. The runner now supports an equivalent `--source-root` mount path and
checks it resolves to its own checkout. Those failed attempts cleaned their own
containers; they are not recorded as passes.

## Delivery boundaries

- Integrate this branch together with the capability-approval worker's source,
  V003 migration and package-restore source. The C branch deliberately does not
  copy or independently edit those owners' Java/proto files.
- The GitHub Actions workflow has not yet run remotely. Local command evidence
  does not establish a green public CI run.

No full unit suite, model call, live business operation, deployment, or repeated
full self-host installation was performed for this CI slice.
