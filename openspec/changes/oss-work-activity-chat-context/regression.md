# Regression evidence

Verified on the public B application, 2026-10-15, through ordinary authenticated UI:

- Manual workflow started from the catalog. The Chat activity rail showed its real name, admission time, manual source, waiting node and original missing-input form. One submission resumed the same run; all three nodes completed. Saved business execution count was one.
- Selecting the completed run added a removable reference without sending a message. Sending a question returned the saved fictional person result. A second question without another reference retained context. Reload preserved messages and references.
- A real scheduler plan emitted a new run at its configured time without any parent Chat association. The rail classified it as scheduled, with plan provenance. One missing-input submission resumed that same run and completed all three nodes. The test plan was disabled after its first trigger.
- A reference to that scheduled result was added to the existing Chat. The assistant correctly contrasted the distinct manual and scheduled results. Saved Chat tool counts were zero for these reference-based answers; neither workflow nor business query was rerun.
- A separate fresh Chat discovered the scheduled run through list_workflow_runs and read its saved result through get_workflow_run_result. All tools were readonly. Both original runs retained one submission and one business query.

Engineering checks: TypeScript/Vite build and source-manifest equality; deployed imports; additive schema migration; owner/environment isolation and pagination against actual saved PostgreSQL records; actual SDK multi-turn checkpoint and tool-schema probes; exact-file secret/boundary scans; git diff --check. Unit test suites were not run, per user direction.

Review corrections: bound attachments by the final serialized UTF-8 JSON size, including escaping, before saving messages. Three quote/backslash/newline/Unicode-heavy references remain within the shared context limit. Source-filter values are explicitly enumerated in the model tool schema to avoid silently empty uppercase queries.

Local desktop and narrow-layout checks covered grouping, reference chips, modal focus restoration and the activity drawer. Public static hashes matched the deployed build. Narrow local checks used browser zoom, not a claimed exact device viewport.

Evidence boundary: explicit business-attention reporting validates real successful execute_ability evidence and saved fact ownership. The initial release had SDK/database read-path coverage; the follow-up public acceptance below adds live model-generated anomaly proof. No generic anomaly detector, automatic remediation, workflow retry, or background-triggered Chat turn was introduced. Historical timestamps/source absent from saved records are not fabricated.


## Business attention follow-up: 2026-10-16

A normal authenticated public B run queried one fictional person under an explicitly supplied, demonstration-only rule: age below 25 requires manual review. The business query returned age 24. All three nodes completed; exactly one execute_ability and one report_workflow_attention call succeeded. No temporary confirmation form was generated in the accepted run. One persisted business attention referenced the actual successful query ToolMessage. The result provider resolved that evidence as AVAILABLE while the workflow remained SUCCEEDED.

The Chat rail displayed this completed run in attention, with its workflow title, time, anomaly title and summary. Clicking Continue in Chat attached the run without sending. A new Chat question used the persisted anomaly and raw evidence to explain the condition, produce three checks and a notification draft. A second turn without another attachment retained context. Both turns had zero tools; no business query or workflow was repeated. Refresh retained the messages and reference. Marking the reminder viewed moved the run out of attention; refresh retained that read state. Viewed means read, not business review completed.

Observed failures were preserved: an unknown fictional ID caused whole-request business rejection; a model attempted to cite an Application load request as report evidence; another run unnecessarily requested confirmation at the display node and was explicitly stopped via UI. Neither failed request was silently retried or converted to success.

The correction registers reporting only for nodes authorized to execute_ability, hides it from each model request until that node has a successful business ToolMessage, and supplies exact allowed references. Extraction is shared with the unchanged backend evidence validator. Node instructions prohibit premature downstream anomaly handling and redundant report-confirmation forms when the condition is already clear. Actual-runtime SDK probes covered missing/user/render/error evidence, successful references, request immutability, and sync/async wrappers. Independent review, deployed module imports, exact-file secret scans and diff-check passed. Runtime source cb96aef was deployed; the B deployment remained 8f11092. No unit-test suite was run.

The first Chat answer loosely suggested confirming/closing the reminder; the follow-up explicitly distinguished read acknowledgement from completed business review. No business-review transition or outbound message was executed. This acceptance establishes a controlled live path, not a guarantee that every model-generated recommendation is precise.
