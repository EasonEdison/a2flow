# Retire Python M authoring

Baseline: origin/main ab5c8df, 2026-10-06. Root explicitly authorized retiring obsolete Python M asset authoring; Python account authentication and B/Runtime remain.

Removed the old management API and its draft/publication/CRUD features, standalone Workflow composer, Ability and A2UI management adapters, and old management deployment entry points. Preserved shared Skill readers, Ability validators and A2UI published-definition validators. Extracted host secret loading to deploy/common/config.py. Realchat still starts its existing B and Runtime hosts.

Account extraction/deletion of the remaining legacy auth files belongs to the account worker. Java management/publication and deployment integration belong to root and the publication worker. Historical apps/management frontend has no active Python host and is retained pending root scope decision.

Verification: 44 retained Skill, Ability and A2UI tests pass. Imports pass for deploy.assets, deploy.realchat.launcher, deploy.attended.bside_app, agent_workflow_runtime.mvp_assembly and all retained registries. a2flow_management is absent from import resolution. Existing host virtual environments supply dependencies; no installation, image build, deployment or database access was performed.

make quality-python passed for the remaining shared typed kernel; git diff --check passed. The PostgreSQL identity test retains B/Runtime DDL and excludes the retired M draft table; its live database path was not run.
