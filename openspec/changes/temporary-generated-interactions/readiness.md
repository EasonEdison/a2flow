# Readiness

IMPLEMENTED AND DEPLOYED; PUBLIC CHAT ACCEPTED. Full public Chat + Workflow gate remains open.

Source `661a7a73c24f1335953aa3afff57bf7e4072c46e` is integrated to both main remotes
and deployed to Runtime/B/frontend. Subsequent evidence-only commits do not change the
deployed application revision.

Public Chat passed required-form, choice+notes and display-only generation, actual submit,
server-side continuation with saved input, local-draft recovery and completed read-only
history. Real PostgreSQL/LangGraph validated Flow wait/resume/result/stop behavior in 29
deterministic checks, then 30 checks with exactly one real model-generated interactive candidate
at the deployed revision (the display branch remained deterministic). This is not a claim of public Workflow real-model acceptance;
that remaining gate stays explicit and the change is not archived as fully accepted.

Known boundary: model-generated output can fail strict validation; errors are explicit and
there is no automatic repair/retry. Drafts are browser-local. Inputs are flat scalar/string-array
schemas; dynamic nested-row inputs and arbitrary business RPC in generated JSON are not supported.
Chat continuation is deduplicated, but a process crash between claim and completion is not a
promise of automatic recovery or business exactly-once execution. A submitted input does not
assert an external business operation succeeded.
