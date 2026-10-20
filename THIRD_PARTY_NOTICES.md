# Third-party notices

The root [MIT license](LICENSE) covers A2Flow-owned code. It does not replace upstream licenses or imply that every dependency or vendored file was independently authored here.

## Vendored A2UI material

A2UI official schema/catalog material is retained under Apache-2.0 in:

- [Java management copy and license](services/management-java/backend/skillfactory/a2ui/v0_9_1/official/LICENSE)
- [Python execution copy and license](services/a2ui-execution/src/a2flow_a2ui/official/LICENSE)

Upstream: [google/A2UI](https://github.com/google/A2UI). Preserve the upstream license and any copyright headers when redistributing these directories. Root MIT licensing does not relicense them.

## Installed dependencies

Java Maven dependencies and npm/Python packages remain under their own licenses. The management frontend has a [dependency-license inventory](services/management-java/frontend/dependency-licenses.json); it is a recorded inventory, not a guarantee that it is current for every lock-file revision or a repository-wide SBOM. Consult package metadata and bundled notices for the exact versions you redistribute.

Management authoring includes owner-authorized adaptations as well as project-specific implementations. This document records known attribution boundaries; it is not a claim of a complete legal or provenance audit. Contributors must identify provenance and compatible permissions for new external code.
