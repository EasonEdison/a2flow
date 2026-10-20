# Bounded Skill package restoration

## Problem and scope

The authenticated management `PACKAGE_VERSION_RESTORE` method accepts a caller-provided URL, including local file URLs, outside the immutable artifact ownership and digest path. Shared ZIP extraction checks destination traversal but not expanded bytes or entry count, including ignored entries. Original URLs may include bearer query credentials in logs.

## Decision

Reject the legacy URL method explicitly. Keep `WORKSPACE_RESET_FROM_VERSION` with BUILD/VERSION sources: server-selected successful publication records, workspace/namespace-scoped database artifacts, digest validation and relation restoration. Keep normal uploaded ZIP authoring. Do not add an external URL allowlist or a new artifact-ID protocol.

Apply a streaming budget to all ZIP entry consumption, including release validation, ignored entries and directory entries. Defaults: 32 MiB expanded total, 8 MiB per entry, 2000 entries. Positive operator-configurable limits fail fast when invalid. Use actual streamed bytes, not declared ZIP sizes. Reject before replacing the current workspace and clean temporary files. The existing 100 MiB compressed input ceiling remains unchanged. Restore/import now stream directly from loaded archive bytes: only bounded expanded output is staged, with no additional compressed temporary file. Memory and concurrent-request quotas remain separate deployment constraints.

## Compatibility

Legacy `PACKAGE_VERSION_RESTORE` callers receive a stable explicit error directing them to published BUILD/VERSION reset. Current frontend has no caller of this legacy method. No network download, arbitrary local ZIP lookup or raw URL logging remains in the service. Existing ownership, draft edit protection, frozen artifact digest checks and relation restoration remain in place.

## Validation

JDK 17 isolated executable probe with synthetic small ZIPs and low limits; no database, network, real account or production operation. Check normal immutable restore/upload, URL rejection, byte/entry limits including skipped payloads, traversal, empty packages, unchanged originals and cleanup. Root owns shared compilation, integration and public deployment acceptance.

Operator configuration, compatibility and probe instructions: [package restoration](../../../docs/package-restoration.md).
