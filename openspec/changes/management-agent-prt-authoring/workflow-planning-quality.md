# Workflow planning quality in management Chat

The management Agent now reads real Skill instructions and bindings through existing detail/workspace tools and checks the candidate identities and PRT release state. Current draft material is not assumed to represent published behavior. Declared dependencies describe available capabilities, not guaranteed calls.

For the same goal, inputs and time, reuse the result of an existing Skill rather than adding the same capability again. Naming a query Skill "summary" does not change its published behavior. A summary of already obtained fields uses the built-in SUMMARY and summaryConfig.prompt. Repetition remains valid for different inputs, different times, or an explicit user requirement. There is no runtime deduplication or automatic mutation of saved workflows.

## Source and checks

Commit 63ee642, integrated at c898409, changes only the management Agent SYSTEM_PROMPT. Six actual management-tool schemas were checked offline, and executable AST excluding the prompt was unchanged. Ruff F/E9, diff-check and the exact outgoing secret scan passed. Broader historical lint findings were not modified; unit tests were waived. Only the management Agent runner was deployed, retaining the prior image and a rollback plan. Java management, B and workflow execution were unchanged.

## Public authoring evidence

A normal management Chat request asked to browse fictional people, query a user-provided identifier at runtime and summarize name/age, using existing published assets. It did not add user-message hints about deduplication. The resulting workflow wf_6e4567c2fa4e4c3faae0885b4c25ced8 contains browse Skill, lookup Skill, and the built-in summary, without a second independent lookup.

Build build_dd39299c1d2d449aa09f4023ee6801cd and deployment deployment_369e6fcc94844b38b4a2ee0840a68773 are effective in PRT at version 1. Management and Runtime digest a1df66d0fdc9bb3424a00978785306f8235c932156be179389ea8240a661bbd9 match. Only three management mutations occurred: create this workflow, update its draft, and deploy it to PRT. Existing Skill result cards came from reads; no existing dependency was edited or republished.

The first B run failed after its list read because the model supplied people/page/pageSize/total to render_application while the published application contract accepts only params={}. The rejection was A2UI_PARAMS_INVALID and produced no card or submission. This failure is retained, not silently retried. A separate explicit acceptance run of the unchanged published workflow included the exact application-parameter contract in its task text; it reached temporary-input waiting. This runtime task clarification is separate from the management creation request, which contained no deduplication hints. The second run eac79550e1d44bf2a405dc2147f9a522 succeeded after one form submission: list 1, resolve 1, summary tool calls 0. Full reload and reopening the saved history preserved the exact evidence JSON, with execution fingerprint e25d6a19f493f1eb357e01530a6a6f23c8142cd765a6340884632a856b3f8579. All three nodes remained SUCCEEDED, with 25 execution facts and one accepted action. This proves the scoped planning and continuation case, not first-attempt rendering reliability. This is model planning guidance and does not guarantee that every future generated plan is minimal.
