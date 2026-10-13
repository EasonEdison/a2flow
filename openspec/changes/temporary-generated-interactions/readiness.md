# Readiness

PRE-DEPLOY CHECKS PASS; public acceptance pending.

Implementation, build/import, isolated PostgreSQL/LangGraph, frontend fixture and controlled
real generation checks passed. Source/deployment/public proof remain separate.

Known boundary: model-generated output can fail strict validation; errors are explicit and there
is no automatic repair/retry. Drafts are browser-local. Inputs are flat scalar/string-array schemas;
dynamic nested-row inputs and arbitrary business RPC in generated JSON are not supported.
Chat continuation is deduplicated, but a process crash between claim and completion is not a
promise of automatic recovery or business exactly-once execution.
