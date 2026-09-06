# use_skill Consumer Requirements

> Owner of final Tool/shared schema: Runtime + `oss-platform-contracts` under main-brain review
> Contributor: `oss-skill-registry`
> Status: **CONSUMER INPUT / NOT A SHARED CONTRACT**

## Purpose

Define what Skill Registry needs from the unified Runtime `use_skill` path without creating a competing Tool schema. The same path must load one immutable Skill release for conversation and Workflow use.

## Model-visible request

The model needs only a logical Skill selection, provisionally：

```json
{"skillKey": "demo/evidence-first-brief"}
```

The final schema may rename `skillKey`. It MUST NOT accept model-controlled：

- `userId`、environment、gray cohort or target version；
- credentials、database/namespace or package locator；
- workflow routing/result fields；
- an instruction to use native directory activation instead。

## Trusted context

Runtime injects, outside model arguments：

- authenticated `userId` and principal；
- current environment：PRT or ONLINE；
- conversation/run/node scope；
- control request identity；
- recorded/effective configuration version evidence。

The resolver and authorization layer must treat only this trusted context as authoritative。

## Resolution requirement

- PRT → PRT current only。
- ONLINE stable user → ONLINE stable only。
- ONLINE gray user → ONLINE gray selected by trusted userId only。
- No cross-environment fallback and no third ONLINE serving version。
- Return one exact immutable Skill release/package reference plus version evidence。
- A missing/forbidden/unavailable Skill fails closed；the model cannot override target selection。

## Success material semantics

A successful Tool result needs：

- resolved logical identity and immutable release/version；
- configuration/version evidence for execution and continue checks；
- `SKILL.md` instructions；
- authorized read-only resource descriptors or opaque handles with normalized `logicalPath`、media type、digest and size；text references and binary assets remain distinguishable；
- content digest；
- compatibility hints such as required Tool names, never authorization。

Do not return credentials, server paths, raw unrestricted locators or authoring metadata。

## Execution semantics

- Runtime adds the returned instructions/resources to the current agent/node context and continues its existing Tool loop。
- Loading does not create a per-Skill LangGraph subgraph or business node factory。
- Conversation and Workflow callers use the same Tool contract and receive the same package bytes for the same trusted context。
- Workflow decides where to invoke a Skill, but Skill publication does not bind a Workflow。
- Tool/material failure is not a generic retry license；Phase 1 node retry remains limited to the approved A2UI cases。

## Admission/version semantics

Every load returns evidence sufficient for Runtime to compare the run's recorded version set with current effective configuration at execution/continue ingress。Mismatch blocks new work and prompts explicit reset；the resolver must not silently serve a frozen old version。

## Required denial tests

1. Model supplies another userId/environment/gray target。
2. ONLINE has no Skill but PRT does。
3. Ordinary user calls authoring/publish rather than use_skill。
4. Caller loads a native SDK directory or raw package locator directly。
5. Package instructions mention an authorized Tool or include scripts/allowed-tools；validation must not misclassify text as execution authority。
6. Workflow caller requests mode-specific rewritten instructions or routing output。
