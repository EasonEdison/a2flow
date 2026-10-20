# Regression evidence

## Source and deployment

Implementation baseline: `1d823cc57b76cda39c7bf85cf1ad0caa06f7893b`, integrated and synchronized to main. Only the B-side source overlays and frontend were activated; the workflow executor was not restarted. Existing image and launcher were retained, with a per-service rollback definition. Four additive processing tables were installed without reseeding or rewriting history.

Frontend TypeScript/Vite build passed. All 71 build-source hashes matched the integrated checkout and all seven public frontend asset hashes matched the build. Actual B-image imports and the real installed SDK composition of processing/reference middleware, SystemMessage and checkpoint persistence passed; projected attachments did not alter the stored user message. Exact outgoing-file secret/proprietary-pattern scans and git diff checks passed. No full unit suite was run.

Backend bounded transaction-rollback PostgreSQL and FastAPI/SSE probes covered request replay (one runner invocation, same message IDs), conflicts, owner/environment/conversation isolation, operation receipts and replay, UNKNOWN no redispatch, card continuation, activity association and explicit resolution. A missing or inconsistent card-task relation now rejects before card action execution; it never becomes ordinary Chat continuation. Completed replay emits the normal done event; active replay preserves saved delivery and does not start a second runner.

## Public acceptance, 2026-10-20 (Asia/Shanghai)

Schedule 5 actually fired at 2026-10-19 22:45. The existing run `3b0232b980284fa989a669db058daf1c` succeeded with three nodes and one real business attention. The exact schedule was disabled through the existing schedule repository, then verified in the public UI as disabled with its completed history retained. No workflow rerun was used for handling acceptance.

The management conversation created and published `workflow-attention-review-record` version 1 to PRT using six existing content capabilities. No new business service, capability, Application or workflow was introduced.

From the scheduled attention's explicit handling entry, Chat 54 created task `handling-1c17d40226f04dae8a6e91283d3ff692`. Initial messages 151/152 invoked use_skill and generate_interaction. A single temporary form collected project title and audience. One submission automatically created continuation messages 153/154 on the same task. The continuation re-admitted the Skill and invoked five business tools: create project, save source, read source, save manuscript, read manuscript.

Business database verification found exactly one project, one source revision and one MANUSCRIPT revision. The three write receipts matched the task's stable request IDs and real result IDs. The manuscript inputRefs used the actual source ID and revision 1. No content confirmation or reminder acknowledgement was created.

The original right-rail attention opened the associated task with all five saved execution receipts. Original-conversation navigation worked. Reload retained the completed card and final result. Full before/after persisted snapshots were equal, including task, operations, turns, business records, receipts, original runtime facts hash and total run count (35).

## Boundaries

Final task state is RESULT_RECORDED, not RESOLVED. Saving this fictional review draft is not completion of a personnel review. Public acceptance intentionally did not click manual resolution. Manual-resolution validation has bounded database/HTTP evidence only. Downstream business idempotency remains the capability's responsibility; no generalized exactly-once guarantee or automatic uncertain-write retry is claimed.
