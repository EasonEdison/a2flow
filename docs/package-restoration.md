# Skill package restoration

Management restores a Skill from an existing immutable publication record. Use the current workspace's reset action, choosing a successful PRT Build or an existing formal version. The server retains workspace edit authorization, draft-state checks, database artifact ownership/digest validation and relation restoration. This does not publish a new version or execute the Skill.

## API compatibility

`WORKSPACE_RESET_FROM_VERSION` remains supported through the authenticated management handler/bizrender envelope:

- `workspaceId`: the workspace the caller can edit.
- `sourceType`: `BUILD` or `VERSION`.
- `sourceId`: an existing successful Build ID for that workspace, or the positive formal version number. Select a returned publication record; do not synthesize a source identity.

The legacy `PACKAGE_VERSION_RESTORE` method no longer accepts caller-selected `packageUrl` values, including `http:`, `https:`, `file:` or unsupported schemes. After existing entry and asset authorization, it returns a business failure with `data.errorCode = PACKAGE_RESTORE_SOURCE_REQUIRED`, `data.fieldPath = sourceId` and a readable instruction to select a published Build/version. The enclosing handler remains its existing SSE/JSON envelope; an HTTP 200 alone is not success. No source URL is fetched, reflected into the error, or logged by restoration code.

No current frontend or tracked CLI calls the legacy method. External API/CLI integrations must migrate to the existing reset method. Uploaded source ZIP import remains supported as an authoring operation; it is not an arbitrary remote URL downloader. This change does not create a new external-import allowlist or a new artifact-ID protocol.

## Extraction limits

The management host accepts these explicit configuration values (environment variables work without source edits):

| Setting | Default | Meaning |
| --- | ---: | --- |
| `A2FLOW_PACKAGE_MAX_EXPANDED_BYTES` | `33554432` | Total streamed uncompressed bytes per archive, 32 MiB |
| `A2FLOW_PACKAGE_MAX_ENTRY_BYTES` | `8388608` | Streamed bytes per ZIP entry, 8 MiB |
| `A2FLOW_PACKAGE_MAX_ENTRIES` | `2000` | All ZIP entries, including ignored files and directories |

Values must be positive and the per-entry byte limit cannot exceed the total. Invalid configuration fails initialization. Limits apply to uploaded imports, immutable restore and release ZIP validation. Actual bytes are counted while streaming; ZIP metadata is not trusted. Ignored `.git`/cache/macOS entries and directory payloads also consume budgets. Stable business errors are `PACKAGE_ENTRY_COUNT_EXCEEDED`, `PACKAGE_ENTRY_BYTES_EXCEEDED` and `PACKAGE_EXPANDED_BYTES_EXCEEDED`, with `fieldPath = package`.

Restore/import stream directly from already loaded archive bytes into a unique temporary directory; the compressed package is not duplicated on the temporary filesystem. On validation or budget failure, the temporary request directory is removed before returning and the original workspace is not replaced. Normal replacement and relation restoration remain the existing transaction workflow. The compressed-input ceiling remains 100 MiB; database/HTTP memory budgets and multiple concurrent requests are separate concerns. A per-archive limit is not a global filesystem quota. Operators must size memory/tmpfs and concurrency together before raising limits.

## Reproducible isolated probe

From the repository root, with JDK 17 and the management dependencies available:

```sh
mvn -f services/management-java/pom.xml -DskipTests compile dependency:copy-dependencies
probe_classes=$(mktemp -d)
trap 'rm -rf "$probe_classes"' EXIT
javac -encoding UTF-8 \
  -cp 'services/management-java/target/classes:services/management-java/target/dependency/*' \
  -d "$probe_classes" \
  services/management-java/backend/storage/db/tests/PackageRestoreGuardProbe.java
java -cp "$probe_classes:services/management-java/target/classes:services/management-java/target/dependency/*" \
  dev.a2flow.management.lifecycle.artifact.PackageRestoreGuardProbe
```

The probe takes no arguments, makes no network/database calls, creates synthetic small ZIPs, uses low per-instance limits, and removes its own temporary directory. It covers normal immutable restore and upload, legacy URL rejection, oversized individual/aggregate/skipped/directory entries, entry count, release validation, traversal, empty input, unchanged workspace and cleanup. Success prints one JSON summary on stdout; failure exits nonzero. Service logs may appear on stderr. It does not establish public deployment readiness or prove the independent published-record/relationship workflow.
