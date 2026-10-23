# State vocabulary verification

Baseline `b3a8e7c`; production and probe candidate `ee8a9ef2ed976720d8177ad8435479b721bd339b`. Scope is vocabulary/navigation, not another execution state machine.

## Preserved authorities and protocols

- ProductTurnStatus maps to chat_turns.status. AgentTurnState maps to agent_chat_turns.state. TurnInspectionStatus is a computed inspect_turn conclusion, not a third database state column.
- StrEnum values remain the original strings; Runtime returns `.value`, so the status is an ordinary string. RuntimeTurnInspection retains its original Literal status annotation and optional result. Independent checks confirm string equality, JSON serialization and hashes; existing fake/string callers need no enum-object migration.
- B's dispatch_lock and native _execution_identity names expose separate responsibilities. Both original lock-key derivations and connection ownership remain. Runtime inspection briefly tries the same native key held by session across model/tool/checkpoint work; it is not the product dispatch lock.
- Runtime SCHEMA is byte-for-byte identical. The native key helper is AST-identical after name normalization and session arguments are identical. Native SQL state constants are now bound string parameters in the verified original order.
- Every B class is AST-identical after normalizing enum literals, inspection variable/lock names and removing documentation strings. B SQL, invalid-inspection error, fencing and two-second status/recheck update are unchanged.

## Focused actual PostgreSQL proof

The existing BUSY case now exercises both original product states: QUEUED remains QUEUED and RUNNING remains RUNNING, next_attempt_at is still about two seconds later, with zero execution during BUSY. Its scan bound accounts for two legitimate task settlements while preserving the actual deadline and no-early-inspection assertions.

A new process probe uses actual ConversationStore.session and its PostgreSQL native lock. While the child owns native execution, inspect_turn returns BUSY and the parent can independently obtain the B dispatch_lock. The child exits abruptly; a SQL read confirms its native row remains RUNNING. With the native lock released, inspect_turn returns NEEDS_REVIEW; real B dispatch blocks without calling iterate. This is not a scripted BUSY result masquerading as an actual lock check.

Independent read-only review checked each native query parameter order, plain-string return, exception path and finally unlock; no scoped blocker was found. Tests use isolated schemas, recorded/scripted execution ports and an actual abruptly exiting child, never an external model or business API.

All eight related groups passed on the same candidate, totaling 429 checks, with no skips. Reproduce via [core probes](../../../docs/core-probes.md). Source validation does not establish deployment, remote CI or public acceptance.


| Scoped group | Checks | Result |
| --- | ---: | --- |
| Wake / locks / inspection (23 PostgreSQL + 12 signal) | 35 | PASS |
| Chat state convergence | 26 | PASS |
| Durable Chat delivery | 37 | PASS |
| Native turn recovery | 4 | PASS |
| Chat write approval | 239 | PASS |
| Workflow write approval | 41 | PASS |
| A2UI write preflight | 38 | PASS |
| Production composition / lifespan | 9 | PASS |

BUSY inspection gaps were 2.027 seconds (original QUEUED) and 2.025 seconds (original RUNNING), with zero execution while BUSY. The existing default idle test ran once for 31.208 seconds, with two candidate scans including startup and no execution; this readability change introduces no new performance claim.

All 34 explicit source files passed strict Mypy, Ruff and format: 2 shared, 15 HTTP, 10 persistence including the actually changed Runtime Chat persistence file, 3 transport and 4 composition. Repository validation parsed 394 Python files and checked entry links/import boundaries. Final diff and outgoing sensitive-data checks passed. No unrelated account/outbox/capability groups, Java/frontend builds or complete historical unit suite were rerun because their implementation was unaffected.

All probe schemas/task containers were removed and the 12 existing self-host/outbox containers were preserved. No public database, external provider/business call, deployment or remote CI run is claimed.
