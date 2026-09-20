# A2Flow management API

This package is the shared management Host contract for all asset kinds. It is
mounted into one Python deployment; feature modules must not create separate
listeners, authentication schemes, draft tables, or publication systems.

## Host contract

Create the ASGI application with `a2flow_management.http.create_app(service,
identity_resolver=...)`. The resolver receives the server-side ASGI scope and
must return an already authenticated `TrustedManagementContext`. The API never
uses request headers, query parameters, or JSON fields as user, role, or
environment authority. Missing or invalid trusted identity fails closed.

The Host selects an environment-bound AssetReader and DraftRepository before
registering features. PRT and ONLINE repositories are separate physical
database bindings. A feature must reject a trusted context whose environment
does not match its repository before draft I/O.

## Assembly

Use `a2flow_management.assembly.create_management_app(...)` with one explicit
environment-local `AssetReader`, `DraftRepository`, namespace and trusted
identity resolver. The factory registers exactly Skill, Ability, APPLICATION
and Workflow. It rejects namespace/environment/validator mismatches and does
not register COMPONENT authoring.

Required source roots are `services/management-api/src`,
`services/capability-registry/src`, `services/a2ui-composer/src`,
`services/workflow-composer/src`, `packages/asset-store/src`,
`packages/contracts/src`, and `services/skill-registry/src`.

## Endpoints

- `GET /management/session`: trusted server identity, environment, registered
  kinds and `canAuthor`; no client-supplied authority.

- `GET /management/assets/{kind}`: published list for USER or ADMIN.
- `GET /management/assets/{kind}/{key}`: published detail.
- `GET|PUT /management/assets/{kind}/{key}/draft`: ADMIN draft read/save.
- `POST /management/assets/{kind}/{key}/validate`: ADMIN validation.
- `POST /management/assets/{kind}/{key}/publication-plans`: ADMIN-only
  immutable publication preparation.

- `GET /management/assets/{kind}/{key}/dependencies`: bounded, environment-local
  upstream and reverse dependency evidence. ADMIN receives saved-draft diagnostics;
  USER receives published evidence only. Exact release selectors never fall back.
- `POST /management/assets/{kind}/{key}/publication-checks`: ADMIN-only validation
  and candidate preparation through the existing flow. It performs no publication
  write and returns `PREPARED_NOT_PUBLISHED` only after validation succeeds.

Publication preparation is not publication. Its response always includes
`status: PREPARED_NOT_PUBLISHED` and `published: false`.

- `GET /management/assets/{kind}/{key}/versions`: USER/ADMIN retained immutable
  version history, current serving selection, and serving digest CAS token.
- `POST /management/assets/{kind}/{key}/publications`: ADMIN-only explicit
  candidate retention plus serving selection.
- `POST /management/assets/{kind}/{key}/rollbacks`: ADMIN-only selection of a
  retained version. This is configuration rollback only; it never compensates
  business effects.

Publish and rollback serialize with bundle imports through the same
namespace-scoped advisory transaction lock, reject stale serving digests and
immutable-version conflicts, and validate the resulting namespace before any
write. PRT selects one current version. ONLINE selects one stable version and
at most one userId-targeted gray version; selecting STABLE finishes gray.
Selected Application-to-Ability version pins are checked for the stable cohort
and every gray user cohort. A single-asset change that would require an atomic
linked-asset upgrade is rejected; coordinated multi-asset publication is
explicitly deferred rather than partially applied.

Bodies are limited to 1 MiB and responses to 2 MiB. Unknown fields, query
parameters, oversized keys, malformed domain identifiers, and invalid target
environment/channel combinations fail with a bounded JSON error code. Error
responses never contain draft content, credentials, connection strings, or
exception text.

No listener starts on import. The existing hash-pinned FastAPI/Starlette runtime
dependencies are reused; this package does not install dependencies itself.

## Skill file workspace

ADMIN file editing uses a separate persistent workspace before committing to the
existing full saved draft. All routes use `/management/assets/SKILL/{key}`:

- `GET /workspace` returns `baseDraftRevision`, `workspaceRevision`, `dirty`, and
  `entries`. Entries include `SKILL.md` first, then resources, each retaining
  `handleId`, `logicalPath`, `mediaType`, `byteSize`, `contentDigest`, and `base64`.
- `PUT /workspace/file` accepts `expectedWorkspaceRevision`, `logicalPath`,
  `mediaType`, and `base64`. It upserts one file, derives size/digest and preserves
  its handle. The response is the new workspace snapshot.
- `POST /workspace/delete` accepts `expectedWorkspaceRevision` and `logicalPath`.
  `SKILL.md` cannot be deleted. The response is the new workspace snapshot.
- `POST /workspace/commit` accepts `expectedWorkspaceRevision` and
  `expectedDraftRevision`, returning `{workspace, draft}`. It updates the saved
  draft and clears workspace dirty state atomically; frontmatter becomes draft
  metadata, while bindings and required tools remain unchanged.

The initial workspace is a read-only projection with revision zero; its first
file mutation persists it. PostgreSQL uses the existing management draft table,
under the reserved namespace `skill-workspace:<sha256(original namespace)>`.
This identity cannot be used as a public asset namespace. No filesystem or new
schema migration is involved. PRT/ONLINE keep their existing separate databases.
A clean workspace follows the latest saved draft; a dirty one retains its base.
Stale file revisions return `WORKSPACE_REVISION_CONFLICT`. Draft changes after
editing began return `WORKSPACE_BASE_DRAFT_CONFLICT` on commit and retain files.
The current slice has no reset/rebase or ZIP import endpoint. Editors should
commit file changes before separately saving bindings/metadata.

File saves allow unfinished frontmatter, but package path, size, digest and text
encoding rules still apply, and SKILL.md must remain nonempty Markdown. Commit
requires supported frontmatter. Publication preparation and HTTP publication
reject `WORKSPACE_NOT_COMMITTED` while saved file changes await commit. Existing
publication remains an explicit separate action; runtime readers never query the
workspace namespace. Published entries pass unchanged through `AssetReader` to
`use_skill`, which exposes instruction text and resource path/handle descriptors.
This slice does not add filesystem materialization or script execution.


## Opt-in PostgreSQL integration

`tests/test_postgres_integration.py` runs only when
`A2FLOW_MANAGEMENT_PG_SOCKET` is set. It expects two disposable databases
named by `A2FLOW_MANAGEMENT_PRT_DATABASE` and
`A2FLOW_MANAGEMENT_ONLINE_DATABASE`. The test creates only application tables
inside those databases; it never creates databases, starts a listener, or
falls back to another PostgreSQL instance.

The recorded AF10 verification used the exact cached PostgreSQL image named in
the task handoff, a unique `--network none --rm` container, tmpfs PGDATA, and a
Unix socket bind-mounted from a task-private temporary directory. No TCP port,
persistent volume, existing database, password, model, or deployment was used.

On 2026-09-15 the opt-in test completed one real PostgreSQL case successfully:
two environment-bound databases were initialized and seeded; draft digest,
optimistic revision and concurrent same-revision behavior passed; wrong
database/environment were rejected; publication preparation left immutable
assets and serving state unchanged; and all four registered modules served
list/detail through the unified Host. Final cleanup evidence was
`container=removed fixture=removed`.
