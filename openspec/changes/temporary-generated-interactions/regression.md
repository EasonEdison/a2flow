# Regression evidence

Baseline: 665893d3338f978c4f3777ff8ac9283c4a099b89. Evidence date: 2026-10-13.

## Source and isolated integration

- Integrated Python imports and 12-component catalog admission passed. Scoped static checks,
  Python 3.11 parsing, TypeScript and Vite production build passed. No unit tests per user instruction.
- Real PostgreSQL and native LangGraph probe passed 29 checks at ee188fc:
  persisted interrupt, new graph/connection restoration, atomic submitted-card/outbox,
  exactly one submission observation and outbox command on replay, correct-node resume,
  structured SUBMITTED values reaching the next node, no second generation or resume execution,
  display-only completion without interrupt, and stopped-run action rejection/read-only view.
  This probe used synthetic Skill data and a deterministic candidate; no model or business RPC.
- Real PostgreSQL B-side continuation claim: two concurrent callers produce one dispatch owner
  and one message pair; repeated card returns the same IDs; another owner is rejected;
  completed assistant content is not overwritten. Nine connections checked isolated schema scope.
- Actual frontend with controlled API fixture: desktop/mobile layout; local draft reload and
  account isolation; submit clears draft; history polling receives continuation without a browser
  messages POST; completed card stays read-only after refresh. A confirmed invalid-field response
  leaves the form editable and a subsequent explicit corrected submission succeeds.
- Six controlled real model calls used only synthetic data: selection+notes passed (4.747s);
  one display candidate failed root restriction, one verification wrapper failed file permissions,
  one failed candidate reception, one diagnosed components as an object instead of an array;
  after admitting the existing Card container as a root and supplying explicit candidate JSONSchema,
  display-only comparison passed (3.572s). Failures were not hidden or automatically retried.
- The root/container restriction, candidate-shape explanation, and Flow display serialization
  compatibility were repaired before deployment. No business data writes were performed.

## Deployment and public acceptance

Pending. Source checks and isolated integration are not evidence of public availability.
