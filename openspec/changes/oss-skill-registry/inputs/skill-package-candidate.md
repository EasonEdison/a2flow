# Skill Package Candidate

> Status: **DOMAIN CANDIDATE / NOT A SHARED RELEASE SCHEMA**
> Shared package reference/publication fields belong to `oss-platform-contracts`.

## Author Format

Use the public [Agent Skills Specification](https://agentskills.io/specification) directory profile：

```text
evidence-first-brief/
├── SKILL.md
└── references/
    └── output-format.md
```

Required `SKILL.md` frontmatter：

- `name`：1–64 lowercase letters/numbers/hyphens，must match the directory。
- `description`：non-empty，maximum 1024 characters。
- optional `license`、`compatibility` and string-to-string `metadata`。
- optional experimental `allowed-tools` is compatibility metadata only。

Body and resources are UTF-8 read-only instructions/material。The package is independent from chat/Workflow entry mode。

## Skill Registry Revision Envelope Needs

The registry domain needs to associate an immutable package with：

- logical `skillKey`；
- author semantic version；
- shared immutable package reference；
- catalog/discovery metadata snapshot；
- package validation fingerprint/result；
- optional `requiredToolNames` compatibility hints；
- audit subject/time and local authoring revision。

It MUST NOT include：

- `WorkflowReleaseRef` or graph；
- route/next-node/candidate-branch fields；
- Workflow-specific result adapter/output；
- model-selected userId/environment/gray target；
- credentials or an unrestricted fetch URL。

Exact identity、reference、publication、version-evidence and error fields are shared-contract decisions。

## Package Reference Consumer Properties

Without freezing schema，Skill Registry requires：

- immutable content digest；
- media type and byte size；
- backend-controlled fetch handle/locator；
- no embedded credential；
- ability to re-check digest/size after fetch；
- environment-local publication association；
- authorization before instructions/resources are returned。

OCI-compatible descriptors remain one transport candidate，not a Phase 1 service requirement。

## Phase 1 Script Policy

The public Agent Skills format allows optional `scripts/`。Phase 1 may retain such bytes for format compatibility，but：

- Registry never executes them；
- `use_skill` returns no execution permission；
- ordinary users have no script-upload/authoring power；
- future execution requires a separately approved sandbox Tool and policy。

## Validation Codes Candidate

These codes communicate domain needs；contracts owner may rename them：

| Candidate code | Condition |
| --- | --- |
| `SKILL_PACKAGE_MISSING_MANIFEST` | root SKILL.md missing |
| `SKILL_PACKAGE_INVALID_FRONTMATTER` | YAML/frontmatter invalid or required field missing |
| `SKILL_PACKAGE_NAME_MISMATCH` | name differs from directory |
| `SKILL_PACKAGE_UNSAFE_PATH` | traversal、absolute、device or escaping symlink |
| `SKILL_PACKAGE_LIMIT_EXCEEDED` | bytes/file count/depth/single-file limit |
| `SKILL_PACKAGE_DIGEST_MISMATCH` | observed bytes differ from shared reference |
| `SKILL_PACKAGE_REFERENCE_MISSING` | SKILL.md references absent resource |
| `SKILL_PACKAGE_INVALID_DOMAIN_FIELDS` | revision envelope includes Workflow/route/context override fields |
| `SKILL_PACKAGE_EXECUTION_DENIED` | package content requests direct execution/permission elevation |

Deterministic package errors block publication and are not automatic Workflow retries。
