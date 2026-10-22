# Chat state convergence validation

## Scope and method

Source baseline: `06962a3`. Acceptance uses the latest schema only. It does not migrate or reset an existing installation. Real PostgreSQL tests run against disposable databases with real transaction/locking behavior and the production repositories; model/provider/business replies are scripted. No public database was written, no live business or model operation was sent, and no service was deployed.

## Checks

| Check | Result and evidence boundary |
| --- | --- |
| Baseline core probes | All nine previous Python groups passed on the unchanged baseline. |
| Full candidate core probes | All ten Python groups passed, including the new convergence group. Existing account guard, outbox, capability approval, native recovery, durable delivery, composition, Chat/Workflow approval and A2UI guards remain covered. |
| PostgreSQL convergence | 26 checks passed, no skips, probe resources removed. Real concurrent request/source registration and alias conflict; final-message/turn transaction rollback using an injected PostgreSQL trigger failure; generation fencing; continuation intent and task binding after a failed materialization; native result/checkpoint corruption and no replay; incompatible schema preserved on rejection. |
| Work activity integration | Real SQL reads the new unified turn relation; actual handling receipt and explicit resolution remain associated. Notification read state and anomaly acknowledgement do not close the business task. |
| Focused delivery/API checks | 29 checks passed with no skips: B delivery/history/cards/production composition and Runtime SSE. |
| Shared and affected Python quality | 31 files passed strict Mypy, Ruff and format checks, including shared contracts, HTTP/persistence/transport and production composition. No type suppression or missing-import exemption was introduced. |
| Independent display comparison | 11 scripted cases compared with baseline ChatDelivery. Public display/wire behavior matched after normalizing delivery sequence, persisted card snapshots and new card-scope metadata; live final projection and direct snapshot repair matched exactly. Covers plain/no-ID text, visible reasoning, multiple model/tool messages, cards, existing-card references and personal Workflow registration. |

The transport journal is not immutable Event Sourcing. A current generation can replace its own sequence; later generations append after saved facts and stale producers are fenced. Result integrity is enforced by checksum plus structural/identity/sequence/part relationships. Unknown execution remains blocked rather than retried.

A pending card does not introduce a new prohibition on ordinary Chat. A subsequent ordinary message may run a new model turn, while the previous card keeps its original ownership and cannot be silently submitted or rebound. A pure EXISTING-card waiting reference is validated independently of this production behavior.

## Reproduction

Use [core probe instructions](../../../docs/core-probes.md). Run the whole Python core suite with `scripts/run_core_probes.py`; to repeat only the new disposable PostgreSQL group, select `--python-probe chat-state-convergence`. The selected probe and cleanup result are recorded in the JSON report. `scripts/verify_chat_state_convergence.py` is the inner entrypoint and accepts only its explicitly named disposable database; do not point it at installation data.

The runner creates its own isolated database/container, mounts source read-only, and makes no external model/business calls. Strict dependency checks use `scripts/check_python_dependency_types.py`. Repository boundaries use `python3 scripts/check_repository.py`, and outgoing whitespace uses `git diff --check`.

## Limits and pre-existing failures

A broader legacy B test selection has the same four failures and two errors on baseline and candidate; Runtime Chat/Skill/SSE has the same nine failures and one error. They concern earlier fake interfaces/tool allowlist expectations, were compared on both revisions, and are not reported as a passing full unit suite. The focused checks above have no skips. Java and frontend code are unchanged and were not rebuilt.

These checks establish source behavior with real persistence, not public real-provider or real-business acceptance. Public schema inventory was read-only and showed older structures. The user explicitly declined compatibility; deploying into that database requires a separately authorized data/installation decision. No automatic migration/reset command is included.
