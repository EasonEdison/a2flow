# A2UI Application contract fixtures

Status: PROVISIONAL / Phase 1 contract evidence for baseline SW-P1-20260907.2. These files are independently authored synthetic examples. They are not copied business assets, production schemas, an approved protocol version, or runtime evidence.

## Scope

- display-only-result-card.application.json demonstrates DISPLAY_ONLY rendering. It never creates an interaction wait and only permits retry after rendering failure.
- interactive-selection-card.application.json demonstrates an INTERACTIVE node/card/form-scoped choice. The Action selects a named shared ResultInterpretationPolicy with successPolicyRef and completes the interaction only because the Application explicitly enables that transition.
- validate-fixtures.mjs checks the local A2UI-domain invariants without dependencies or network access.

Run:

    node --test packages/a2ui-contract-fixtures/test/validate-fixtures.test.mjs
    node packages/a2ui-contract-fixtures/validate-fixtures.mjs --directory packages/a2ui-contract-fixtures/fixtures

## Ownership boundaries

The fixture fields are consumer-shaped candidates pending cross-domain review. SW-CONTRACTS-P1-CANDIDATE.1 is named but not approved; it is an input to review, not a frozen dependency:

- packages/contracts owns trusted userId/environment resolution, effective version comparison, public Release references, control-request dedupe and the ResultInterpretationPolicy schema; Runtime owns the single pure interpreter.
- Runtime owns render_application execution, Surface instantiation, persistence, interruption/resume, version admission and Action dispatch.
- packages/a2ui-host, owned by the digital-employee task, maps accepted components to the browser and returns node-bound Actions.
- This package owns only Application strategy examples and local validation of those examples. It does not define a shared schema or an alternative Runtime evaluator.

Runtime identity, environment and credentials are deliberately absent. PRT versus ONLINE and ONLINE gray selection occur before Application resolution through the shared trusted-context contract. A protocol profile is left as PENDING_CROSS_DOMAIN_REVIEW rather than freezing the earlier A2UI version recommendation.

## Behavioral boundaries

- DISPLAY_ONLY does not pause.
- INTERACTIVE pauses and ordinary chat cannot resume it.
- Render success, Action transport success, configured business success, interaction completion, Skill completion and Workflow completion are different facts.
- Output schema validity, success-policy match, Action call success and interaction completion are also separate facts.
- Finalizer cannot override business facts or bypass a required interaction.
- Node-level retry reasons are limited to RENDER_FAILED, ACTION_CALL_FAILED and ACTION_RESULT_NOT_SUCCESS.
- Retry reasons are unique; duplicated allowlist entries are rejected.
- controlRequestId dedupe is not a business exactly-once guarantee; called API backends own business idempotency.
- Version mismatch is checked before execution, continue and Action dispatch and requires an explicit reset, with no automatic restart or business replay.
- Action policies require non-empty unique identities and bidirectional one-to-one coverage with component events.
- abilityReleaseRef rejects explicit floating values such as latest/default/draft; shared contracts still own actual release lookup.
- Both credential and credentials fields are rejected explicitly; this is not a heuristic keyword filter.
