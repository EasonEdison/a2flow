# Frontend validation — 2026-09-22

- `npm install --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org`: completed; exact versions recorded in package-lock.json.
- `npm test`: 33 discovered test files, 33 passed, 0 failed, 0 skipped. Existing assertion-level tests run inside each file.
- `npm run build`: strict TypeScript check and Vite production build passed; 2929 transformed modules. Output is generated under dist/ and excluded from source delivery.
- Source diff whitespace check: no whitespace errors.
- Private package/domain scan: no private @es dependencies or company endpoint/domain references remain in the frontend source. Explicit legacy KRPC/TRUSTED_COOKIE rejection tests remain intentionally.
- Dynamic bundle checks cover CommonJS named/direct/default exports, AMD, window namespace and lexical namespace bundles; rendering succeeds and missing dependencies/components fail explicitly.

No backend or browser acceptance is claimed. Employee directory/binding integration, component bundles rebuilt against the public image module, authentication Host integration, and real authoring/publish/run interactions remain runtime acceptance requirements. No server files, deployment, or public Git state were changed by frontend validation.

## Manual management delivery

- Agent rails, open buttons, generated-context buttons and AI validation/repair buttons are not rendered. The shared chat hook skips session history/recovery when paused. Dormant adapters and review parsers remain source-compatible for a separately approved later release.
- All CODING_* and AUTHORING_* calls, streaming chat and CAPABILITY_SKILL_CREATOR_CONTEXT are rejected before fetch. The policy test iterates the actual method registry and asserts zero network calls for these paused methods. RUNTIME_VALIDATE is deterministic sample parsing/contract checking/preview, not Agent execution: the test proves that its API reaches fetch and preserves the backend result. The original UI did not call that API; its existing manual render_component input preview remains available, without adding a new page feature. Deterministic validation, action scanning, component previews, binding, file editing and direct publication remain enabled.
- SKILL_FACTORY_CONFIG remains necessary for manual specialist/domain/cluster choices; no Agent dependency is required to complete manual forms. A2UI/component pages no longer fetch config solely for Agent setup.
- Environment enum values/map keys are PRT/ONLINE. Existing Java wire identifiers remain unchanged: preprod fields, PREPROD_CURRENT, PACKAGE_PUBLISH_PREPROD, RELEASE_PREPROD_DEPLOY and preprod/current are compatibility identifiers, not additional environments.
- Gray userId normalization accepts the complete signed64 canonical decimal-string range including zero and negatives, rejects overflow/noncanonical numbers, and never converts through Number.
- No standalone PREPROD environment literal/key remains in frontend source. Browser interaction and backend integration are still not proven by these source tests.
