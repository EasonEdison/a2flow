# Regression and evidence

## Delivery and actual public acceptance — 2026-10-14

Runtime source `67ade5cbc3cedbbf580c060ecfc61890c5847c70` is integrated to both main remotes and deployed for the Java management service and dedicated Python management Agent. The frontend build is `c4395a1`; unchanged B/Workflow execution services retain their previous deployments.

Authenticated Chrome management conversation `4f7b68c9f9f34f32822122c5d09cc9cf` created the following assets through real model-selected management tools, not preinserted fixture rows. Final creation turn `5743462db58f477487e3b6e32a9036ca` completed with 48 tool calls. Earlier turns and partial failures remain in history; this was an iterative acceptance run with concrete defects repaired, not an uninterrupted first-attempt success.

| Kind | Asset | PRT version | Deployment |
| --- | --- | --- | --- |
| CAPABILITY_ACTION | cap_draft_8b7c1b9a49664e2898ab1966b792744f | 1 | deployment_4e76c0bada6c4989877ba5df4f779aba |
| CAPABILITY_ACTION | cap_draft_5f88b8cba4474d2bbaf1e3f660173b87 | 1 | deployment_10b536b38d1d4269b53df5ce04953878 |
| A2UI_APPLICATION | management-chat-demo-people-browser | 1 | deployment_42110f10e7ee4111a44b99e37ae5dc8d |
| SKILL | management-chat-demo-people-browse | 1 | deployment_627473ffc7aa48abb592dcbf575be4ef |
| SKILL | management-chat-demo-people-resolve | 1 | deployment_c273620fd428467e987069dc7eeda6b0 |
| ORCHESTRATION_CONFIG | wf_e47bd91dd95b49d58a703013e13b4f71 | 1 | deployment_896a65c7c89b49cc9ddccdbb510d0dd2 |

The two business capabilities reuse registered read-only ListPeople/ResolvePeople interfaces and passed actual digest-bound PRT dry runs. The A2UI is DISPLAY_ONLY. The Workflow contains browse_people -> resolve_people -> __summary__; compilation and PRT dependency gates passed. The two previous invalid camelCase Skill drafts remain as failed acceptance history; explicitly named legal replacements were created through Chat.

Actual Runtime `RpcAssetReader`, `load_skill` and `resolve_workflow` resolved all six published materials and their complete dependency closure. This proves publication and material loading, not a new B-side Workflow execution or business-write run.

## Refresh and continuation

After completion, a full browser reload retained the saved conversation and publication results. Exact read-only database snapshots before/after were identical: 5 turns, 400 events, last sequence 450, 63 mutation-journal rows (49 succeeded, 14 rejected), no unresolved mutations. Fingerprint: `e888977c53d5faf76f5455d416d7f47d9c5ccfbbf7e930e849b31afa44931a41`. Tool-completed counts include receipt reconciliation events; they are not an execution count. Refresh did not create a new turn or repeat a write.

Follow-up same-asset change/publication acceptance is pending authenticated browser continuation: the next send was rejected after the account session expired, before a new turn was admitted.

## Failure and durability evidence

- Invalid capability code, missing dry-run evidence, invalid binding mode and invalid Workflow graph fields were explicitly rejected. The model corrected declared Workflow schema errors before saving; no silent normalization or fallback was added.
- Two prewrite domain exceptions had initially been classified UNKNOWN: a missing presentation binding and a native Skill key violation. Later writes were blocked across turns. Specific validation errors and early key admission now give definite rejection; generic uncertain publication remains UNKNOWN.
- Each old UNKNOWN receipt was corrected by a separate reviewed, exact-request operator CAS only after archiving the original record/stack and verifying prewrite failure and absent affected state. Native publication absence was verified in both databases. No asset outcome was invented, no Python journal was manually edited, and no uncertain operation was replayed. Normal ReadReceipt propagated the definite result. Original failed-turn history remains.
- RUNTIME_VALIDATE is an optional legacy output-sample preview. Its FAILED/PARTIAL results are preserved and cannot be presented as a passed native Skill gate. Workflow preview errors/null compiledPlan are also rejected accurately.

## Verification boundaries

- JDK 17 full Java package/dependency build; frontend TypeScript/Vite build; Python compile checks; relevant direct protocol probes passed. Unit tests were waived by the user.
- 23 isolated real PostgreSQL/native Deep Agent SDK checks covered identity isolation, idempotency, request conflicts, persisted checkpoints, UNKNOWN across turns/restart, receipt reconciliation, singleton admission and no grant exposure. These checks used a synthetic model and fake Java service; they do not substitute for the public model acceptance above. The dedicated probe schema was removed after preserving evidence.
- 8 native SDK checks covered large-result offload/history reads, current-thread isolation, traversal/host-file/window rejection. The management-only StateBackend exposes only current-session native cached result/history paths; no host filesystem or arbitrary file tools.
- Anonymous public management access returned 401. Browser session expiration also denied a later send. Trusted model schemas exclude identity/environment; Java ingress enforces administrator/Cookie/Origin, internal callback uses existing mTLS plus a scoped grant. No browser Cookie is sent to tools.
- Exact outgoing files passed sensitive-data/company-pattern scans and git diff checks. New release mounts and previous container configuration/image references were retained for rollback. Both changed services were running without restart/OOM at verification.

No ONLINE publication, new business backend, or business write was performed. Unknown write recovery remains deliberately conservative; operator evidence is required where no definite receipt exists.
