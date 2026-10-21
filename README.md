# A2Flow

**Agent workflows with interactive UI — from a request to an inspectable result.**

[中文](README.zh-CN.md) · [Getting started](docs/getting-started.md) · [Current architecture](docs/current-architecture.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)

A2Flow explores a practical question: how can an agent complete business work when it needs reusable tools, missing information from a person, and a durable record of what actually happened?

An administrator can describe a requirement to create and publish Skills, business abilities, A2UI assets and Workflows. A user can create a personal workflow in chat, run an existing workflow, or schedule a published preset workflow. When required input is missing, the model generates a temporary interaction; submitting it continues the same task. Saved workflow results and reported anomalies can be brought into chat without rerunning the original business operation.

## A concrete journey

```text
Scheduled workflow → query with a registered ability → report a business anomaly
  → activity rail → user chooses to handle it in chat
  → temporary form for missing input → submit once → continue the same task
  → save a review draft through existing tools → inspect linked receipts
```

Saving a draft is not resolving a business anomaly. Marking a notification viewed is not completing a task. A2Flow preserves these distinctions in storage and presentation.

## Try it

Requirements: Python 3.11+ for repository checks; Node 22.12+ and npm for the UI.

```sh
git clone https://github.com/EasonEdison/a2flow.git
cd a2flow
python3 scripts/check_repository.py
cd apps/digital-employee/web
npm ci --ignore-scripts --no-audit --no-fund
npm run build
npm run preview
```

Open **http://127.0.0.1:4173/employee/?preview=fixture**. This explicitly labeled, local fixture demonstrates workflow cards and state presentation. It does **not** call a model, database or business service, and is not the full authenticated product. See [getting started](docs/getting-started.md) for the current management build and the prerequisites for real execution.

For a new installation, follow the [complete self-hosting guide](deploy/selfhost/README.md): public image builds, isolated PostgreSQL/Redis, explicit administrator creation and mTLS configuration. Initialization and asset publication are separate steps; no default password or sample business writes are hidden in startup. The historical operator Compose files still require existing infrastructure. See the [acceptance record](openspec/changes/production-foundations/readiness.md) for the verified scope.

## What is implemented?

Snapshot: 2026-10-20. Evidence describes specific acceptance paths, not a blanket production-readiness guarantee.

| Capability | Current scope and evidence |
| --- | --- |
| Management authoring and chat | Java control plane with a Python agent; create/reuse assets and publish to PRT. [Evidence](openspec/changes/management-agent-prt-authoring/readiness.md) |
| Temporary interaction | Model-generated forms in Chat and Workflow; valid submission automatically continues the owning task. [Evidence](openspec/changes/temporary-generated-interactions/readiness.md) |
| User workflows | Chat creation, personal workflow registration and execution. [Evidence](openspec/changes/personal-workflows-in-chat/readiness.md) |
| Business ability nodes | Model-assisted arguments and missing-input interaction. [Evidence](openspec/changes/workflow-capability-nodes/readiness.md) |
| Work activity and results | Manual/scheduled results and anomalies linked to chat; explicit handling and saved receipts. [Evidence](openspec/changes/oss-workflow-attention-handling/readiness.md) |
| Execution limits | Current product loader supports 1–8 sequential nodes and an optional summary. Arbitrary DAG orchestration is not claimed. |

Historical specifications also discuss parallel graphs and broader future capabilities. Use the [current implementation map](docs/current-architecture.md), not an old proposal, to assess what ships.

## Engineering choices

- **Java management, Python execution.** Asset authoring/validation/publication is separate from model execution and business services.
- **Frameworks used directly.** Deep Agents provides the model/tool loop; LangGraph supplies graph/checkpoint/interrupt primitives. Platform code owns authentication, asset resolution, admission and product state.
- **Durable Chat delivery.** Request identities and a persistent continuation inbox cover accepted-but-not-started work; saved completion events repair lost history without replaying the Agent. Uncertain execution requires review. [Scope and validation](openspec/changes/chat-turn-reliability/readiness.md).
- **Controlled tools.** The same Skill enters through `use_skill` in Chat and Workflow. Trusted identity and environment come from the service, not model arguments.
- **Explicit failure semantics.** Stop prevents new work; it does not undo an already dispatched business write. Unknown outcomes are not automatically retried. Control-request deduplication is not business exactly-once.
- **Evidence over screenshots alone.** Readiness documents separate source checks, deployment and observed execution. There is no published scale benchmark or high-availability guarantee.

## Code map

| Path | Responsibility |
| --- | --- |
| `services/management-java/` | Current Java asset control plane and management React UI |
| `services/agent-workflow-runtime/` | Generic agent/workflow engine and tool integration |
| `services/b-side-api/` | Business workspace APIs, conversations, activity and handling records |
| `apps/digital-employee/web/` | Current business workspace React UI |
| `services/scheduler-mq/` | Schedule and event delivery integration |
| `services/a2ui-execution/`, `services/capability-execution/` | Presentation and business execution boundaries |
| `services/content-service/` | Independent example content domain |
| `packages/` | Shared contracts, persistence and fixtures |
| `openspec/changes/` | Design decisions and scoped validation evidence |

[Interview/code walkthrough](docs/portfolio-walkthrough.md) · [Known limitations](docs/quality-roadmap.md) · [Security policy](SECURITY.md) · [Documentation index](docs/README.md)

A2Flow-owned code is MIT licensed. Vendored components and dependencies keep their upstream licenses; see [third-party notices](THIRD_PARTY_NOTICES.md).
