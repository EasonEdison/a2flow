# Readiness

IMPLEMENTED, DEPLOYED AND PUBLIC CHAT + WORKFLOW ACCEPTED for the bounded temporary-interaction scope.

Public Chat passed required-form, choice+notes and display-only generation, one-submit
server-side continuation, draft recovery and completed read-only history. The internal
continuation input is not displayed as a user-authored message.

Public Workflow was created and published through the normal management UI with two
synthetic Skills. One real host-model run generated an input card, waited durably, and
reopened after page reload. One browser submission automatically resumed the original
node through the durable outbox, executed the downstream Skill using the saved input,
and completed the summary node. The same run reached SUCCEEDED and remained read-only
after refresh. No manual resume, follow-up chat message, business RPC, or model retry
was used to complete that run. Detailed identities and counts are in regression.md.

Deployed source layers: Runtime and B at 7fc58475b66b1cef6627bf28a4eb6f532c408981;
management Java classes at c2619e87b5569ec63a2131fcb5bcc363f198fe69;
employee frontend at a49143c2e74588931d5f630d28f98a85270e6a8e. The later source
revision includes the earlier backend changes. Deployment receipts and prior versions
are retained privately for rollback. Evidence-only commits do not replace application artifacts.

This verifies two existing Flow Skill nodes using a newly generated temporary card;
it does not claim automatic generation of an entire Flow or arbitrary business systems.
The new management-to-native publication supports validated linear workflows and rejects
unsupported execution semantics rather than discarding them.

Known boundary: generated output can fail strict validation, with explicit errors and
no automatic repair/retry. Drafts are browser-local. Inputs are bounded flat scalar or
string-array schemas; nested rows and arbitrary business RPC in generated JSON are not
supported. Chat continuation is deduplicated, but a process crash between claim and
completion is not a promise of automatic recovery or business exactly-once execution.
A submitted input does not assert that an external business operation succeeded.
