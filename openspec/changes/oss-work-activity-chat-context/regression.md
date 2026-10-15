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

Evidence boundary: explicit business-attention reporting validates real successful execute_ability evidence and saved fact ownership. This branch has SDK/database read-path coverage, not a live model-generated anomaly acceptance run. No generic anomaly detector, automatic remediation, workflow retry, or background-triggered Chat turn was introduced. Historical timestamps/source absent from saved records are not fabricated.
