# Chat reliability verification

## Scope and evidence

Verification date: 2026-10-21. All database probes used synthetic records in isolated local PostgreSQL containers, with cleanup verified. No production credentials or business records were used.

- Integrated B-side durable probe: **37 checks PASS** via `scripts/run_core_probes.py --python-probe chat-reliability`. Covers concurrent receipt/dispatch, request digest conflicts, parameter-based routes, ownership, continuation rollback/restart, completed Runtime projection repair, busy/uncertain no-replay, queue ordering, stale dispatch fencing and poison continuation isolation.
- Native Runtime recovery probe: **4 checks PASS** through `scripts/verify_chat_turn_recovery.py` and the core runner. Covers process termination, session locking, completed replay and uncertain-turn refusal. Runtime targeted suite: **11 tests PASS** including existing persistence and observation coverage.
- B-side history/cards/SSE targeted checks: **6 PASS**.
- Frontend: production build PASS; **13 targeted checks PASS**. Full suite has 28 passing and two pre-existing data-URL/TypeScript import harness failures, independently reproduced on the unchanged baseline.
- Existing approval probes: Chat **243**, Workflow **41**, A2UI preflight **38** checks PASS. These validate approval behavior, not public deployment.
- Both new probes are included in the existing core CI runner's default selection. Local runner success is not a claim that hosted CI already passed.
- Known unrelated baseline failures: four older Runtime loop tests (outdated fake/signature/error-boundary assumptions); the historical B-side RunRef fake workflow start returns 500. They were not broadened into this change.

## State and recovery boundaries

Product tables own accepted requests, message projections, continuation intents and dispatch generations. Deep Agents owns its model/tool loop; the Runtime adapter records authoritative turn completion and public replay events. Dispatch generations fence stale product writes; they do not authorize model or business execution. Only NOT_STARTED may dispatch; BUSY defers; COMPLETED rebuilds the projection; NEEDS_REVIEW never automatically replays.

Card completion and continuation intent are transactional. Intent materialization is idempotent and independently retried with persisted backoff. Invalid bindings are held for review without starving unrelated messages. This is local preparation, not a business-call retry.

## Future release prerequisites

1. Back up product and Runtime databases and record deployed component versions.
2. Apply the additive B-side `schema.sql` additions, including continuation recovery fields and turn dispatch generation. Run the existing `ConversationStore.setup()` migration for Runtime turn facts. Existing self-host bootstrap already calls these setup paths; do not blindly rerun business-data seed scripts on an existing installation.
3. Release B frontend and B API together: POST `/api/conversations/messages` takes `conversationId` and `clientRequestId` in the JSON body; GET `/api/conversations/messages?conversationId=56` takes the conversation ID in query parameters. The old path-ID message routes are removed. Other resource routes are unchanged. Refresh old browser bundles before resuming sends.
4. Release the matching Runtime adapter before enabling durable dispatch. Verify readiness tables and ownership checks.
5. Public acceptance still needs ordinary conversation, missing-input continuation and write-approval continuation, refresh/duplicate submission, and final saved results. Do not reset or replay historical uncertain turns to manufacture acceptance.

No rollout was performed in this source-only task. External side-effect reconciliation remains outside these two batches.
