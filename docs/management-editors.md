# Management form editors

The management web app exposes form-first authoring for SKILL, ABILITY, COMPONENT, APPLICATION, and WORKFLOW drafts. There is no whole-document JSON mode in the product UI. Every form edits the same per-asset canonical buffer, replaces only the selected path, and preserves fields outside the supported form contract.

## Supported form controls

- SKILL: metadata, Ability and Application binding workbenches, and a database-backed file workspace. Tool grants are platform-derived and are not author-managed.
- ABILITY: read-only key, operation/default policy references, input binding rows, credential slot declarations, and typed JSON editors for schemas and result policies.
- APPLICATION: read-only identity, interaction mode, parameter schema, Action/dependency rows, contract-aligned component workbench, local safe preview, surface template JSON, and read-only safety policies.
- WORKFLOW: read-only key/topology, ordered node rows, and sequence preview.

Malformed stored structures remain untouched and are rendered read-only with reload/server-repair guidance. Complex fields may still use scoped JSON textareas inside their owning form section; these use per-asset pending buffers. Typing never changes the canonical draft, Apply is the only operation that updates it, and Discard requires explicit confirmation before restoring the canonical value. Pending text survives asset switches. Parent/child overlap is locked in both directions, and any pending field blocks save, validation, and candidate preparation.

A revision conflict preserves both canonical edits and exact pending text. Reload cancellation or failure preserves them; only a confirmed successful reload adopts the server document/revision and clears pending state. All controls use the existing busy lock, revision/CAS save flow, validation, prepare, explicit publish, history, and rollback paths.

The APPLICATION workbench reflects the existing flat `surfaceTemplate.components` array and `Column.children` ID references. It supports `Column`, `Text`, `ChoicePicker`, and `Button`, preserves unknown keys and malformed rows, and reports duplicate, dangling, cyclic, unreachable, unsupported, oversized, and binding/sample issues without automatic cleanup or reference repair. Component IDs remain immutable in the property panel; malformed structures are not silently rewritten.

Preview input and rendered state are local per-asset buffers and are never persisted. Preview validates explicit sample JSON before adapting supported components, is depth/size bounded, renders text as React text rather than HTML, and never loads images, opens links, submits forms, calls providers or executes Actions. Button clicks only produce a bounded `SIMULATED / LOCAL` event record with resolved context arguments; they do not imply business success or workflow completion. Desktop and narrow layouts are presentation-only.

The Skill binding workbench follows a catalog/current-bindings layout. Bind and unbind submit the complete outgoing relation snapshot and report success only after the server returns the new draft revision. The generic relation store remains authoritative; the UI does not infer success from a click or duplicate relation truth into asset-specific extension JSON.

The forms provide client-side shape feedback only; backend validation remains authoritative. The permanent browser suite uses intercepted synthetic fixtures and proves UI behavior and payload construction only; it is not backend validation evidence. SKILL frontmatter is never rewritten automatically. APPLICATION mode changes never rewrite fixed policies or components. Non-SEQUENTIAL workflow topology is preserved but reported as not publishable. Binary upload, live execution/rendering, arbitrary components, credentials, and trusted identity editing are not provided. New text files may be created in the database-backed Skill workspace, but no local file upload control is exposed.
