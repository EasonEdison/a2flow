# Regression and evidence

## Delivery and actual public acceptance — 2026-10-14

Initial management acceptance source `67ade5cbc3cedbbf580c060ecfc61890c5847c70` was integrated to both main remotes and deployed for the Java management service and dedicated Python management Agent. The management frontend build is `c4395a1`. B/Workflow execution services retained their previous deployments at that acceptance stage; the later B execution and its deployed fixes are recorded below.

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

Actual Runtime `RpcAssetReader`, `load_skill` and `resolve_workflow` resolved all six published materials and their complete dependency closure. That check proves publication and material loading only. The separate real B-side read-only Workflow execution is recorded below; no business-write run is claimed.

## Refresh and continuation

After completion, a full browser reload retained the saved conversation and publication results. Exact read-only database snapshots before/after were identical: 5 turns, 400 events, last sequence 450, 63 mutation-journal rows (49 succeeded, 14 rejected), no unresolved mutations. Fingerprint: `e888977c53d5faf76f5455d416d7f47d9c5ccfbbf7e930e849b31afa44931a41`. Tool-completed counts include receipt reconciliation events; they are not an execution count. Refresh did not create a new turn or repeat a write.

Follow-up same-asset change/publication: PASS after reauthentication, 2026-10-14 10:54 Asia/Shanghai. The user signed into a different existing administrator account; the original private conversation correctly remained inaccessible. A new authenticated conversation `0317fd2f4d0a4759b8d9d45bf409c247`, turn `63d09699d4ef42ea8ced4c5439442367`, modified the existing Browse Skill through normal domain authorization, without changing ownership or conversation access. It completed 17 tools, including only three mutations: file save, workspace save and PRT deployment.

The requested sentence was added in two description locations in SKILL.md. Comparing retained immutable Runtime materials showed that removing exactly those two sentence occurrences reproduces the prior file byte-for-byte; every other file, dependency and required tool is unchanged. Asset ID remains `skill-389824b97e6f3ee2b2f219d49a10ed32cd3f835c11b2544a2e8379b2cca529f5`. Runtime version changed from `java-73bf7d909cbda224bf4623dc8df8c180f32f893ea1a7662f116d378459e21ed9` to `java-c0a80864ac327c299d55b808e4dd6f185de721a38ba6c8c015d5e0c2fefb1e30`. All five other asset version IDs are unchanged and all six materials remain READABLE.

Actual PRT build `build_b70ccb6535dc4c2d81047dc93f62b201`, deployment `deployment_5a599bdcfd58459899dbb5718939940e`, digest `04c1d4b376c13efd78ffa6a38039cda9ae34cefce6f6298296052131e214c917`, status EFFECTIVE. This is PRT build #2 for target version 1, not a semantic v2 release: the existing active-change lifecycle permits multiple immutable PRT builds before sealing a formal release. The earlier acceptance shorthand “v2” was inaccurate; no lifecycle rule was changed merely to force a display-number increment.

A second browser reload retained the updated result with identical before/after snapshots: 1 turn, 37 events, 3 mutations, last sequence 487; fingerprint `bbfb8801be636a622b8aac36f68ce308afb6fef74e98e0edc1ed4256e35576f8`. No unresolved mutations or repeat publication.

## Public B Workflow execution and recovery — 2026-10-14

The coordinator verified the Chat-authored Workflow `wf_e47bd91dd95b49d58a703013e13b4f71` in authenticated public Chrome after integrated main `3c178785a37620a963347bf190e6f6f9bdd1ae01` was deployed. This deployment updated the single Runtime source file for non-waiting interaction snapshots and the B static frontend; it did not introduce a new business service or asset backend.

Run `35aca777fa5240f2af4a8ad5b510e96f`, control `dca23a63675e4318ac41b5aec357eaba`, completed in PRT. All three nodes — `browse_people`, `resolve_people`, `workflow-summary` — were SUCCEEDED. Persisted execution facts contained 8 MODEL, 6 TOOL, 3 NODE and 3 FINALIZER records: 20 total, all RETURNED. The real read-only ListPeople and ResolvePeople calls returned the same five synthetic person IDs, `001` through `005`, with ages 26, 31, 24, 29 and 35 respectively.

There was one DISPLAY_ONLY card and one COMPLETED, non-waiting interaction, with zero Actions. The coordinator expanded the A2UI and final summary in public Chrome and verified their rendered content. This is real read-only execution acceptance, not a new interactive-submission acceptance.

After a full reload, opening My Runs and selecting the same run restored the same card and summary. Before/after persisted counts and fingerprint were identical: `89321bc9b2867e805c65946cb81e3a1b36aa3c0bfc31d0aa4aecd763f063d06c`. Recovery did not add execution facts or replay business calls.

The first run `e09dc3e1a2ac410f9c5754ef8c7d0cca`, control `d07f116d8b7f40de871afcc98a017cf3`, remains FAILED with an UNCONFIRMED control. Its failure exposed a non-waiting snapshot defect: read-only completion normalization applied only to temporary displays, leaving a published DISPLAY_ONLY snapshot incompatible with the native completed-interaction contract. Fix `59516dd90167715ab426233d2d444161ba6a7207` applies the existing read-only completion shape to every non-interactive internal snapshot; it preserves the separately saved published card definition. B UI fix `f0b7fb63bc0e722853017322e0e511db72dacf2a` exposes uncertain starts, prevents concurrent double submission and offers explicit My Runs refresh without automatic retry. The failed run and its original evidence were retained; the successful run above is a distinct execution, not a rewritten failure.

Pagination clicks were not exercised. The completed history card is read-only, while the model's summary suggested moving to another page. That suggestion exceeds the available history-card behavior and is a non-blocking output-copy issue for this acceptance; no pagination functionality or Action success is claimed.

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
