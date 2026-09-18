# Management form editors

The management web app offers Form and full JSON modes for existing SKILL, ABILITY, APPLICATION, and WORKFLOW drafts. Both modes edit the same per-asset JSON text buffer. Opening or switching modes does not rewrite the draft; form changes immutably replace only the selected path and preserve other fields.

## Supported form controls

- SKILL: metadata, SKILL.md, tool/Ability/Application string rows, and read-only resources.
- ABILITY: read-only key, operation/default policy references, input binding rows, credential slot declarations, and typed JSON editors for schemas and result policies.
- APPLICATION: read-only identity, interaction mode, parameter schema, Action/dependency rows, contract-aligned component workbench, local safe preview, surface template JSON, and read-only safety policies.
- WORKFLOW: read-only key/topology, ordered node rows, and sequence preview.

Invalid full JSON remains in its asset buffer and blocks Form mode, save, validation, and publication until repaired. Complex JSON fields use separate per-asset pending buffers: typing never changes the canonical draft, Apply is the only operation that updates it, and Discard requires explicit confirmation before restoring the canonical value. Pending text survives mode and asset switches. Parent/child overlap is locked in both directions; a full JSON change to the same canonical path marks the pending field conflicted rather than overwriting its exact text. Any pending field blocks save, validation, and candidate preparation.

A revision conflict preserves both canonical edits and exact pending text. Reload cancellation or failure preserves them; only a confirmed successful reload adopts the server document/revision and clears pending state. All controls use the existing busy lock, revision/CAS save flow, validation, prepare, explicit publish, history, and rollback paths.

The APPLICATION workbench reflects the existing flat `surfaceTemplate.components` array and `Column.children` ID references. It supports `Column`, `Text`, `ChoicePicker`, and `Button`, preserves unknown keys and malformed rows, and reports duplicate, dangling, cyclic, unreachable, unsupported, oversized, and binding/sample issues without automatic cleanup or reference repair. Component IDs remain immutable in the property panel; full JSON remains the escape hatch.

Preview input and rendered state are local per-asset buffers and are never persisted. Preview validates explicit sample JSON before adapting supported components, is depth/size bounded, renders text as React text rather than HTML, and never loads images, opens links, submits forms, calls providers or executes Actions. Button clicks only produce a bounded `SIMULATED / LOCAL` event record with resolved context arguments; they do not imply business success or workflow completion. Desktop and narrow layouts are presentation-only.

The forms provide client-side shape feedback only; backend validation remains authoritative and may reject unknown fields. The permanent browser suite uses intercepted synthetic fixtures and proves UI behavior and payload construction only; it is not backend validation evidence. SKILL frontmatter is never rewritten automatically. APPLICATION mode changes never rewrite fixed policies or components. Non-SEQUENTIAL workflow topology is preserved but reported as not publishable. Resource uploads, asset creation/deletion, live execution/rendering, arbitrary components, credentials, and trusted identity editing are not provided.
