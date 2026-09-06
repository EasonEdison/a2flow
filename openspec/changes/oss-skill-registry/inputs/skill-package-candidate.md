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

- `name`：1–64 lowercase ASCII letters/numbers/hyphens；must not start/end with a hyphen or contain consecutive hyphens；must match the parent directory。
- `description`：1–1024 characters。
- optional `compatibility`：1–500 characters when present。
- optional `license` and string-to-string `metadata`。
- optional experimental `allowed-tools` is compatibility metadata only；its presence neither grants permission nor causes deterministic rejection。

`SKILL.md` and text references are UTF-8 read-only instructions/material。`assets/` may contain images、templates or other bytes；they are validated and loaded through opaque media type/digest/size descriptors rather than universal UTF-8 decoding。The package is independent from chat/Workflow entry mode。

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
- per-resource media type/digest/size so text and binary assets remain distinguishable；
- environment-local publication association；
- authorization before instructions/resources are returned。

OCI-compatible descriptors remain one transport candidate，not a Phase 1 service requirement。

## Phase 1 Validation versus Execution Policy

The public Agent Skills format allows optional `scripts/` and experimental `allowed-tools`。Phase 1 separates deterministic publication validation from actual Tool execution authorization：

- Registry validates structured metadata、paths、limits、digest and references；it never executes package content。
- Natural-language mentions such as “use execute_ability” are ordinary instructions，not a denial trigger and not authorization。
- The presence of `scripts/` or `allowed-tools` may produce a compatibility warning but does not by itself fail a structurally valid package。
- `use_skill` returns no execution permission；Runtime authorization remains Tool-owned。
- Only a structured authoring/revision `executionProfile` requesting an unsupported executable mode may return `SKILL_EXECUTION_PROFILE_UNSUPPORTED`。
- Future script execution requires a separately approved sandbox Tool and policy。

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
| `SKILL_EXECUTION_PROFILE_UNSUPPORTED` | structured revision requests an unsupported executable profile；never inferred from prose |

Deterministic package errors block publication and are not automatic Workflow retries。
