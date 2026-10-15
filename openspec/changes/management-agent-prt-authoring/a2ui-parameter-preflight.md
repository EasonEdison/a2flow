# A2UI parameter preflight and review

## Problem and change

A model could read the correct Application paramsSchema, then send arbitrary business output as rendering parameters. The execution service rejected those parameters, but the resulting remote exception stopped the entire Workflow node instead of giving the model useful correction feedback.

The shared RPC asset adapter now checks parameters against the current admitted Application contract using the execution service's Draft7 dialect. Both stable rendering and generated layouts use this check. It runs before activation, card persistence, layout model calls and generation progress events. Only this dedicated local, undispatched parameter rejection is handled by the native SDK as an error ToolMessage with the contract and bounded safe schema paths. Input values are not echoed. The model can correct the next call in the same execution while retaining earlier successful results. The required-tool finalizer does not count the rejected call as a completed render.

The implementation never silently deletes parameters, invents defaults, restarts a node or retries business operations. Identity, authorization, malformed contracts and remote failures, including unknown outcomes, continue to fail. Execution-service validation remains authoritative if a publication changes between preflight and activation.

## Source and checks

Implementation commits 043b87f and a108338 were integrated at 2af4d5d. Five runtime files changed. Independent review and root review passed after moving preflight outside generation_trace to prevent false generation-failed events. Fifteen offline SDK contract probes passed: legal empty and nonempty input, missing/extra/wrong-type fields, safe nested paths, malformed contracts, admission failure, generation rejection before dispatch, remote error propagation, synchronous/asynchronous error status, finalizer evidence, and the same tool receiving bad then correct input with one activation and one saved card. AST, scoped Ruff F/E9, helper Ruff, no-new-lint comparison, exact secret scan and diff-check passed. The historical broader style findings were not expanded. The user waived unit-test work.

Runtime and B services were deployed from clean, equal main/origin/main/github/main at 2af4d5d. The prior image and rollback configuration were retained. Management, frontend and published assets were unchanged.

## Public verification

The unchanged PRT Workflow wf_6e4567c2fa4e4c3faae0885b4c25ced8 completed as run 0686674fdc244927999d1c5150f12eab. The original business-only task contained no parameter-contract hints. The browser displayed the people list, accepted one submission of fictional demo-person-003, continued automatically and summarized the correct name and age. All three nodes succeeded. Rendering succeeded once with valid empty parameters; this natural run did not trigger the correction branch. Error-to-corrected-call behavior is established by the offline SDK probes, not claimed as a live correction event. Direct Agent calls were list 1 and resolve 1, with zero summary tool calls; the Application internal load is counted separately below. Full browser reload and reopening this saved history preserved the exact evidence JSON and all call/submission counts. Execution fingerprint: f875a2a001397a2c18c6ee5235db0b9d739c90f70ae45e8554f2fd36d691a363.

## Additional review findings

The earlier evidence's list count of 1 measured Agent execute_ability calls only. The published browse Application also has a list loadBinding, so a successful render adds an internal list invocation. This is inferred from the immutable publication and deterministic execution path; it is not an independent RPC audit total. A later optimization should clarify whether the Skill or Application owns that read, and retain a safe execution summary for observability. This fix does not rewrite existing Skill/Application semantics or add runtime deduplication.
