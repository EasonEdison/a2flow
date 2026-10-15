# Application-owned loading and execution observations

## Change

The browse Skill and its A2UI Application both queried the same list. The Skill now delegates display loading to the Application and retains only its Application binding. The Application still owns its existing load and pagination capabilities. The lookup Skill, capabilities and saved Workflow definition were not changed.

Management Chat planning now reads the actual Application parameter schema, load bindings and request mappings before choosing dependencies. It omits a redundant direct query only for the same goal, inputs and time. Independent business decisions, different inputs, different times and explicit repeated reads remain valid. There is no runtime cache, forced deduplication or automatic retry.

Runtime dependency discovery exposes a safe load contract: binding identity, action code and parameter-source types, with parameter paths only for application parameters. It excludes constants, trusted identity values and mapping expressions. Application build identity is checked against the admitted publication. Declared bindings are not execution evidence.

The execution protocol adds optional request_id and phase fields to execution summaries. Actual returned LOAD summaries are preserved in the initial observation across later Actions, and passed through Chat and Flow restoration. They contain identifiers/status rather than business arguments, results or credentials. Old summaries without those fields remain unknown. These counts describe returned and persisted execution summaries, not raw network attempts or cache hits. A failure before the summary is returned retains that observability limitation; safe stage logs provide separate diagnostic evidence.

## Source, deployment and review

Backend commit 7993ebc and management prompt commit 2a446fc were integrated and deployed at 8bfefd4. Thirteen actual DTO/RPC/SDK probes passed alongside the fifteen parameter-preflight probes. Root and independent review, AST checks, incremental lint, exact outgoing secret scan and diff-check passed. Existing broader lint findings were not expanded. Unit-test work was waived by the user.

Runtime, B and execution services were deployed with verified source/protocol overlays at their actual import locations, retaining prior images and rollback configurations. The management Agent received the prompt update. Import preflight passed; all affected containers were running without restarts or OOM flags at final inspection.

## Publication boundary and additional repair

The real management Chat turn updated the browse instructions and bindings, but then attempted to create a release change despite an existing ACTIVE change. The domain rejected this before snapshot construction or persistence; the generic dispatcher nevertheless reported an unknown outcome and blocked later writes in that turn. That historical failure is preserved.

After confirming the exact no-write boundary, the existing change was published once through the normal management detail UI. It produced a new effective PRT build at version 1, with render_application as the only required tool and no direct capability binding. The Application dependency remains. This was a normal manual publication, not a successful Chat publication in the failed turn.

Commit 309b55c adds a dedicated RELEASE_ACTIVE_CHANGE_EXISTS validation exception at that pre-write branch and maps only this exception to deterministic rejection. The tool catalog instructs the Agent to inspect and reuse an existing ACTIVE change. Other IllegalStateException failures remain unknown, and historical receipts are not rewritten. JDK 17 packaging and real domain/dispatcher/tool-service probes passed: existing ACTIVE rejects without snapshots or writes, replay performs no write, ordinary unrelated failures remain unknown, and a normal new change writes once in memory. The fix was deployed with management code 2e866a5. A subsequent live read-only Chat completed; a new live mutation hitting this rejection was not forced.

## Public execution evidence

An explicit run of the unchanged PRT Workflow used the ordinary business request to display people, collect an identifier at runtime, look up that person and summarize name/age. No parameter-contract or deduplication hints were added.

The browser displayed five fictional people from the first page. One submission of demo-person-003 automatically resumed the lookup and completed the summary. All three nodes succeeded. Persisted evidence showed zero direct Agent list calls, one successful Application LOAD, one identifier lookup, zero summary tool calls and one accepted submission. The summary referred only to the selected identifier. Initial LOAD metadata survived the Action.

After full reload and reopening history, the complete execution evidence JSON and call/submission counts were unchanged. Execution fingerprint: 63010221f5eb0ca2c1860d965cd3cc322b092991bc8630c472aaf2aed98fdedc. This is bounded proof of the tested published assets and run, not a guarantee that every future model plan is minimal.
