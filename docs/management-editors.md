# Management form editors

The management web app offers Form and full JSON modes for existing SKILL, ABILITY, APPLICATION, and WORKFLOW drafts. Both modes edit the same per-asset JSON text buffer. Opening or switching modes does not rewrite the draft; form changes immutably replace only the selected path and preserve other fields.

## Supported form controls

- SKILL: metadata, SKILL.md, tool/Ability/Application string rows, and read-only resources.
- ABILITY: read-only key, operation/default policy references, input binding rows, credential slot declarations, and typed JSON editors for schemas and result policies.
- APPLICATION: read-only identity, interaction mode, parameter schema, Action/dependency rows, surface template JSON, and read-only safety policies.
- WORKFLOW: read-only key/topology, ordered node rows, and sequence preview.

Invalid full JSON remains in its asset buffer and blocks Form mode, save, validation, and publication until repaired. Complex JSON fields require an explicit Apply action, so invalid partial text remains visible instead of being discarded. All controls use the existing busy lock, revision/CAS save flow, validation, prepare, publish, history, and rollback paths.

## Limits

The forms provide client-side shape feedback only; backend validation remains authoritative and may reject unknown fields. SKILL frontmatter is never rewritten automatically. APPLICATION mode changes never rewrite fixed policies or components. Non-SEQUENTIAL workflow topology is preserved but reported as not publishable. Resource uploads, asset creation/deletion, live execution/rendering, arbitrary components, credentials, and trusted identity editing are not provided.
