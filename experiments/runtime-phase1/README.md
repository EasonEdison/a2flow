# Runtime Phase 1 feasibility spike

This directory is an isolated, disposable feasibility probe. It is not the
product Runtime and it does not define shared contracts.

## Scope

- Deep Agents and LangGraph public extension points only.
- Synthetic Skill material and deterministic Tool calls only.
- The integrated `skillweave_contracts` adapter plus the Pydantic Tool-argument
  boundary consume the approved `SW-P1-SUBSET-01` use_skill/trusted-context
  definitions; wire revision remains
  `SW-CONTRACTS-P1-CANDIDATE.1`.
- The integrated `evidence-first-brief` package bytes and A2UI fixture are read
  directly from this repository.
- Offline Anthropic `MockTransport` records real provider serialization without
  using a real key or network.
- No model key, business data, external write, public service, or second
  Workflow scheduler.
- PostgreSQL is the only acceptable persistence gate. Tests that do not need a
  checkpointer may run before PostgreSQL is provisioned, but they do not prove
  persistence readiness.

## Candidate dependency set

- Python 3.11.13
- deepagents 0.7.13
- langchain 1.4.0
- langgraph 1.2.11
- langgraph-checkpoint-postgres 3.1.2
- psycopg-binary 3.3.5

The first attempted langgraph 1.2.10 pin was rejected by the resolver because
the selected LangChain release requires langgraph 1.2.11 or newer. The
PostgreSQL checkpointer also needs either system libpq or a Psycopg
implementation; this spike uses the binary wheel to avoid changing system
libraries. Its LGPL-3.0-only package metadata is an explicit review item, not
an approved production dependency decision.

`requirements.lock` is the exact 59-package freeze of this task-owned venv. It
does not modify or compete with the root lock owned by main-brain.

## Evidence boundaries

- Deep Agents' implicit file, shell, and subagent Tool names are explicitly
  excluded through a provider Harness Profile; the scripted model binds only
  Runtime-owned Tools.
- The Anthropic wire test forces strict Tool binding and proves that the
  serialized second request contains model-facing Tool content but not the
  ToolMessage artifact or evidenceRef.
- The scripted model deliberately calls `use_skill`; this proves framework
  wiring, not that a live model cannot bypass a required call.
- The A2UI probe proves DISPLAY_ONLY return and INTERACTIVE interrupts bound
  to run/node/application/version/tool-call identity. Action validation and
  resume remain PostgreSQL-gated.
- The explicit RED reproducer under `red_reproducers/` observes that an A
  interrupt returns after B1 and prevents B2 from reaching its next superstep.
- One bounded AsyncPostgresSaver probe verified process A interrupt/exit and
  process B read/resume/join for the native branch-subgraph candidate. The
  secret-safe bootstrap fix was not rerun against PostgreSQL; concurrency,
  scoped retry, stop/restart, and live-model behavior remain unverified.

## Run

~~~bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/contracts/src:services/skill-registry/src:services/capability-registry/src:experiments/runtime-phase1 /home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python -m unittest discover -s experiments/runtime-phase1/tests -v
~~~

Every behavioral adapter test must first fail because the named behavior is
missing, then pass after the minimum implementation. Import, dependency,
network, and PostgreSQL availability failures are not valid RED evidence.
