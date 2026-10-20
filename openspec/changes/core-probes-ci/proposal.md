# Core probes as a public regression gate

## Problem and scope

The public jobs compile sources and validate Compose syntax. Existing real
PostgreSQL account-admission and transactional-outbox probes have passed isolated
acceptance, but future contributions do not automatically rerun them.

Add a bounded, no-model gate that reuses these probes, plus the independently
owned Java capability-approval and package-restore probes. This does not replace
the completed fresh self-host acceptance or introduce a full unit suite.

## Design

- A Python entry point owns a uniquely named, loopback-only disposable PostgreSQL
  container, ephemeral credentials and empty databases; it accepts no application
  DSN. It runs the two Python probes sequentially and removes its own container.
- Each subprocess has a deadline; timeout terminates its process group. CI also
  has a job deadline and an always-run cleanup restricted by the run label.
- Java probes use JDK 17 and existing Maven classes/dependencies, no business host.
- Reports distinguish probe checks, resource cleanup and failure. No model keys,
  private installation files, production database or external business are inputs.
- Trigger on runtime, deploy, contracts, Java and probe changes. Preserve current
  static/build checks. Publish only bounded synthetic result artifacts.

The coordinating agent also assigned one integration change: self-host schema
bootstrap must explicitly apply the approval worker's V003 consumption migration
after V002. This branch depends on that worker's migration being integrated and
does not create a second migration or modify approval Java sources.

## Validation

Run the existing probes against a new local PostgreSQL container using a source
export, check that no container/private DSN survives, and exercise a controlled
failure to confirm nonzero exit and cleanup. Run Java probes once their owners
deliver them. Check workflow syntax, repository links and `git diff --check`.
GitHub execution is a separate result from local execution of identical commands.
