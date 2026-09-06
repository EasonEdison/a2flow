# SkillWeave implementation baseline SW-P1-20260907.2

Status: phase 1 execution authorized by the user on 2026-09-07. This baseline supersedes conflicting earlier proposed designs. Authorization is not implementation or runtime evidence.

## Authority and coordination

main-brain is the sole user-facing coordinator. It owns decision transmission, worker acknowledgement, interface review, scoped implementation release and consolidated acceptance. Workers report engineering issues to main-brain, not through the user. A Git merge or delivered message alone is not acknowledgement or review.

Only independently restated product requirements and public sources may enter this repository. No proprietary code, private schemas, internal endpoints, screenshots, credentials or real business data. This document is independently authored for this project.

## Accepted decisions

1. M owns four authoring platforms: Skills, business abilities, components/Applications and multi-Skill Workflows. B contains the digital-employee frontend/backend and a separate business-independent Agent/Workflow Runtime. The Runtime must not import product scenarios or UI copy.
2. Runtime language is Python. Use Deep Agents SDK through public Tools, Middleware, Backend, Store and Checkpointer extension points, with LangGraph as the actual Workflow execution/checkpoint/interrupt foundation. Do not fork framework source or build a second custom Workflow scheduler. Verify exact SDK versions, public APIs, licenses and resource requirements before pinning. Other service languages remain engineering choices for main-brain review.
3. PostgreSQL is the only persistence engine for development, integration and deployment reference profiles. No SQLite/MySQL profiles or fallback. Single-host deployment must not imply single-process correctness: verify shared-state operation with multiple stateless workers.
4. A Skill is AI-executed instructions/resources, not a fixed business subgraph. The same Skill must work in conversation and Workflow without Workflow-specific output fields or custom business-node factories. Generic framework model/Tool mechanics are not a business subgraph.
5. All Skill usage enters through `use_skill`. Abilities and Application rendering also enter through authorized Tools (working names `execute_ability` and `render_application`). All share trusted backend user/environment resolution. The model must not choose another user's identity, environment or credentials. Native SDK Skill-directory activation is not an alternate first-version path. Descriptive discovery metadata is distinct from authorized body/resource loading.
6. B has PRT and ONLINE environments; M and Runtime may share deployments. ALL asset types use separate PRT and ONLINE databases. `userId` is the only identity/gray-targeting term. PRT reads its current version only. ONLINE reads ONLINE stable or ONLINE gray, never PRT. During ONLINE rollout at most two versions serve; afterward one serves. Shared publication and configuration reading have one owner, not four independent implementations.
7. Version identifiers are recorded for comparison. At execution/continue/Action ingress, a mismatch with the effective configuration blocks new work and prompts explicit Workflow reset. Do not continue on frozen old assets, silently migrate, auto-restart or replay business calls. Keep this lightweight; historical records are not deleted by this policy.
8. First-version Workflow supports sequence, conditions and parallel branches, launched manually from the conversation sidebar. User input is bound to a specific node/card/form; ordinary chat does not implicitly resume a Workflow or select a waiting node.
9. An independent AI decision node chooses one configured legal candidate from predecessor results. Skills need no special routing fields. If AI cannot decide semantically, show configured choices using an interactive A2UI selection card in that node; route to the user's choice without AI reselection. Technical failure behavior must not be silently conflated with uncertainty.
10. Downstream Skills and final summarization receive all predecessor final results/statuses by default. Persisted intermediate Tool results are read on demand through a read-only retrieval Tool, never by re-executing the business call. Exact schema, selection and context budgets are engineering work.
11. A2UI configuration owns DISPLAY_ONLY versus INTERACTIVE. Display-only rendering does not pause. Required interaction does. Configuration also determines Action business success and whether that success completes the interaction. Finalizer reasoning cannot override business facts or bypass required interaction; render/Action success alone is not automatically Skill success.
12. A waiting parallel branch blocks its join but not independent progression: while A waits, B1 must be able to finish and proceed to B2 before A resumes. At the join, success, actual allowed skip or failure of an allow-skip node permits joining; a required-node failure blocks. Preserve true failed/skipped status. Never auto-skip merely because a node is waiting. LangGraph `thread_id` is not an OS thread or a distributed lock; prove the mapping rather than assuming one graph invocation provides this behavior.
13. First-version node retry is limited to A2UI rendering failure or Action call failure/results failing the configured success condition. Preserve completed predecessors and independent branches. No generic Skill model/script/non-A2UI Tool retry or internal recovery engine. Audit SDK default retry behavior so it does not silently expand these boundaries. Explicit interaction persistence/resume remains required.
14. Accepted stop prevents new nodes, model/Tool rounds, workflow-affecting Actions and retries in every branch. Keep completed facts and late outcomes from already-dispatched calls without new progression, Finalizer or conversion to success. Stopped runs cannot resume; historical cards become read-only and backend rejects their operations. Stop is not business rollback.
15. Restart creates a fresh run from the entry with no inherited context, checkpoint, results, completion flags or interactions. Do not inspect old business outcomes to gate it. No Workflow business reconciliation, compensation, transaction, rollback or cross-run deduplication. Called API backends own business idempotency/retries. Platform requestId deduplication concerns control requests only, not business exactly-once guarantees.
16. Ordinary users can browse M assets and use authorized B chat/Skills/Workflows/cards. Administrators create/edit/publish assets. Read-only M access does not mean read-only B execution. Do not expose authoring or script-upload powers to ordinary users.
17. Distinguish conversation history, cross-session memory and knowledge retrieval. Reuse mature knowledge components; Deep Agents is not a complete zero-development knowledge-base platform. Lightweight personal-memory view/delete/disable in conversation settings is conditionally approved if low cost, not a separate platform. Disable long-term reads/new writes without disabling current chat; memory deletion is not chat deletion. Assess cost first and escalate material expansion.

## Authorization delta PY-01

On 2026-09-07 the user explicitly permits replacing/upgrading this server's system Python if needed for implementation. This supersedes the former prohibition; it is permission, not a requirement to replace it immediately or evidence of completion. Runtime owns dependency/compatibility checks, a recoverable change plan and post-change verification; main-brain coordinates the single host-level executor. Do not treat missing replacement authorization as a blocker. This does not authorize changes to unrelated services, other system packages, public deployment or secrets.

## Not approved / not phase 1 implementation assumptions

- Exact knowledge-base product scope, unrestricted user uploads, demo real-world business-write authority and live-model provider/secret configuration.
- Public deployment, new exposed ports, Nginx/firewall changes, existing unrelated service changes or destructive data operations.
- Arbitrary cyclic graphs, multi-agent employee swarms, unrestricted shell/script execution, general internal Skill recovery, business transaction/reconciliation infrastructure.
- A transport/protocol or service language merely because an old worker draft proposed it. Shared interfaces need coordinator review.

Synthetic project-authored fixtures and scripted-model test doubles may validate technical behavior. Label them explicitly; they are not live-model or business-runtime evidence and do not decide public-demo permissions.

## Superseded proposals to remove from active designs

TypeScript/LangGraphJS as Runtime baseline; preview/stable as deployment environments; ONLINE gray reading PRT; sellerId as a second targeting identity; per-Skill fixed business subgraphs; mandatory Skill routing fields; frozen-version continuation; generic Skill retries/recovery; Workflow-owned business idempotency and restart reconciliation. Preserve history if needed, but do not leave these as active first-version requirements.

## Public reference entry points

- https://docs.langchain.com/oss/python/deepagents/overview
- https://docs.langchain.com/oss/python/deepagents/customization
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.langchain.com/oss/python/langgraph/graph-api
- https://www.postgresql.org/docs/current/

References are research entry points, not evidence that a version/API combination has been installed or validated. Owners verify current primary sources for their concrete design.
