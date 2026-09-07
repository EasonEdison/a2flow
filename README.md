# SkillWeave

[中文](README.zh-CN.md) | English

SkillWeave is a general-purpose AI application platform that connects reusable Skills, business abilities, A2UI Applications, and multi-Skill Workflows with a digital-employee experience.

Its architecture separates four management platforms—Skill registration, business ability registration, A2UI composition, and Workflow composition—from the digital-employee frontend/backend and a business-independent Python Agent/Workflow Runtime.

## Architecture at a glance

- **Author and publish:** manage reusable assets with shared publication and environment-aware configuration resolution.
- **Execute:** use Deep Agents SDK for Agent execution and LangGraph for multi-Skill graph execution, with PostgreSQL as the only relational persistence engine.
- **Interact:** display A2UI results or pause for required node-bound interaction according to Application configuration.
- **Reuse:** invoke the same Skill from conversation or Workflow through `use_skill`; call business abilities and Applications through controlled Tools.
- **Isolate:** PRT and ONLINE asset databases stay separate; ONLINE gray rollout selects ONLINE versions by trusted userId.

These are architecture commitments, not a list of fully shipped capabilities.

## Documentation

- [Complete architecture — English](docs/architecture.en.md)
- [完整平台架构 — 中文](docs/architecture.zh-CN.md)
- [Documentation index / 文档目录](docs/README.md)
- [Workstreams](docs/workstreams.md)
- [Confirmed phase 1 baseline](openspec/changes/skillweave-phase1/baseline.md)

## Current status

As of 2026-09-07, implementation prioritizes the Python Agent/Workflow engine. The repository contains shared-contract and registry core modules, A2UI fixtures, and isolated framework experiments. Complete M-side editors, the digital-employee product, and a deployable Runtime are not delivered.

The Runtime experiment records 31 passing tests and bounded PostgreSQL cross-process evidence. It remains **NO READY** for product acceptance; live-model behavior, full interaction/control paths, and multi-instance conflicts still require work. See [readiness](openspec/changes/oss-agent-workflow-runtime/readiness.md), [regression evidence](openspec/changes/oss-agent-workflow-runtime/regression.md), and the [experiment guide](experiments/runtime-phase1/README.md).

## Repository

| Directory | Contents |
| --- | --- |
| `docs/` | Bilingual architecture guides and collaboration overview |
| `packages/contracts/` | Shared schema candidates and approved Python adapters |
| `packages/a2ui-contract-fixtures/` | Synthetic Application fixtures and validation |
| `services/skill-registry/` | Skill registry core modules |
| `services/capability-registry/` | Ability registry core modules |
| `experiments/runtime-phase1/` | Agent/Workflow framework feasibility experiments |
| `openspec/changes/` | Proposals, tasks, specifications, and evidence |

All source and examples are independently authored from sanitized requirements and public references. Initial single-host operation is a deployment choice, not a high-availability claim.
