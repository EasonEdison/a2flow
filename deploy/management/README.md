# Private management preview Host

This directory is the protected composition root for the four existing A2Flow
management modules: Skill, Ability, Application, and Workflow. It reuses
`create_management_app`, `AssetReader`, `PostgresAssetRepository`, and
`PostgresDraftRepository`. Import and factory creation do not connect to
PostgreSQL, create tables, seed assets, start a model, or open a listener.

The preview is fail-closed. Headless checks may send exactly one Bearer token
from an owner-only Host file. A browser instead submits that token once to a
same-origin login bootstrap and receives a random process-local, two-hour,
HttpOnly, `SameSite=Strict` cookie. Restarting the Host invalidates the cookie.
The token is never returned to the browser, copied into the UI bundle, placed in
a URL/query, or injected into anonymous proxy requests. The resulting `userId`,
environment, and roles come only from protected Host configuration. Client
identity headers and all management API query parameters are rejected. The ASGI
server address must be loopback; a public bind is rejected even with valid auth.

## Explicit Host configuration

Set these outside the repository:

- `A2FLOW_MANAGEMENT_DATABASE_URL`: explicit DSN for one already-initialized
  PostgreSQL database.
- `A2FLOW_MANAGEMENT_DATABASE_NAME`: exact database name verified on every
  repository connection.
- `A2FLOW_MANAGEMENT_ENVIRONMENT`: `PRT` or `ONLINE`, matching the database's
  `a2flow_asset_environment` row.
- `A2FLOW_MANAGEMENT_ASSET_NAMESPACE`: exact already-seeded namespace; the
  current MVP fixture uses `a2flow-mvp-activity-planning`.
- `A2FLOW_MANAGEMENT_VALIDATOR_FACTORY`: trusted operator factory; the existing
  four-kind MVP assets use `activity_planning_demo:bundle_validator`.
- `A2FLOW_MANAGEMENT_USER_ID`: fixed authenticated preview principal, encoded as canonical signed 64-bit decimal text (for example `101`). The optional guest principal uses the same format. IDs are integers inside the service and decimal strings in browser JSON.
- `A2FLOW_MANAGEMENT_ROLES`: `ADMIN`, `USER`, or the comma-separated exact set.
- `A2FLOW_MANAGEMENT_AUTH_TOKEN_FILE`: absolute regular file owned by the Host
  process identity, mode `0600` or stricter, containing one 32–4096 byte ASCII
  token. Generate a new preview token; never copy an existing credential.
- `A2FLOW_MANAGEMENT_STATIC_DIRECTORY`: absolute path to the already-built
  `apps/management/web/dist`, including `index.html`.
- `A2FLOW_MANAGEMENT_BROWSER_ORIGIN`: exact browser origin for login and unsafe
  cookie-backed API requests, for example `http://127.0.0.1:14176` for an SSH
  tunnel or `http://47.110.84.69` behind a front proxy. It is never inferred
  from a request Host header. Loopback is the safe private-preview default; a
  public origin is an explicit operator decision and must terminate TLS in
  front or accept plaintext token/session risk.

There are no defaults for database, namespace, identity, roles, validator, or
authentication or browser origin. `create_app_from_environment()` fails before
serving when any value is absent, static UI is unavailable, the origin is not
loopback, or the token file is not protected.

## Source factory

Programmatic hosts can construct `ManagementPreviewConfig` and call
`create_management_preview_host(config, validator=..., bearer_token=...)`.
The returned object exposes the real PostgreSQL reader and draft adapters for
inspection, but construction makes no connection. Supplying neither static
directory nor browser origin creates a headless-only app; supplying exactly one
is rejected. For a browser ASGI server, use the environment factory only after
the preview plan below is separately released:

```bash
python -m uvicorn deploy.management.app:create_app_from_environment \
  --factory --host 127.0.0.1 --port 8766
```

This command is documentation, not evidence that a listener was started. The
loopback HTTP cookie is intentionally non-`Secure` only for this SSH-tunnel
preview; it is not a production authentication design. Do not change the bind
to `0.0.0.0`, publish the port, add a public reverse-proxy route, or place the
token in source, a URL, UI bundle, shell history, or logs.

## Isolated acceptance command

From the repository root, use the project's Python environment with its declared
dependencies installed and export the existing source roots before either command
in this section (the repository is not installed as one root Python package):

```bash
export PYTHONPATH="packages/contracts/src:packages/asset-store/src:services/skill-registry/src:services/capability-registry/src:services/a2ui-composer/src:services/workflow-composer/src:services/management-api/src:examples/activity-planning"
```

The command below is the single reviewed entry point for real management
acceptance. Direct invocation of the PostgreSQL test file cannot accept arbitrary
database names or DSNs; it requires an owner-only fixture plan and verifies each
random fixture identity inside its database before schema setup. The runner checks
Python dependencies and a local Docker endpoint before any mutation. It requires
an explicit opt-in, a new absolute output directory, a running Docker daemon, and
the exact pinned PostgreSQL image already present in the local cache. It never
pulls an image, publishes a host port, accepts an external DSN, or reuses an
existing database. It creates a distinct database and namespace for every test
case inside one task-owned, resource-bounded, network-disabled container,
initializes schemas and synthetic assets explicitly, exercises the real ASGI and
PostgreSQL paths, writes sanitized test counts and failing case IDs, and removes
only resources whose unpredictable invocation marker, exact container ID, name,
and directory marker all match.

```bash
python -m deploy.management.acceptance \
  --authorized-isolated-fixture \
  --output-directory /absolute/new/path/management-acceptance
```

A missing Python dependency, local Docker CLI/daemon/context, or cached image exits
nonzero, records PostgreSQL as `NOT_RUN`, and never prints `VERIFIED`. Remote
Docker endpoints are rejected before mutation. A zero-test or skipped suite is
not accepted as PostgreSQL evidence, test execution is bounded, and teardown
failure changes aggregate status to `FAILED`. `unit`, `browser`, and `deployment`
remain separate `NOT_RUN` fields because this command does not substitute
PostgreSQL acceptance for those gates. The pinned image entrypoint, password-file
handling, and `POSTGRES_INITDB_ARGS` are source-configured but remain operationally
unverified until the real command runs. Host-mounted Unix sockets require a Docker
host sharing the host filesystem topology; Docker Desktop cross-VM socket behavior
has not been verified. Run offline guards with:

```bash
python -m unittest deploy.management.test_acceptance
```

## Offline verification

Run with the repository's existing environment and source roots; no dependency
installation or database is required:

```bash
python -m unittest deploy.management.test_app
```

The tests cover real adapter assembly without connection I/O, missing and wrong
authentication, JSON 401 API behavior, browser login/cookie/static serving,
fixed-Origin CSRF rejection, USER versus ADMIN authoring, server-owned identity,
identity-header/query rejection, loopback enforcement, and protected regular
token-file permissions.

## Exact 30-minute real-PostgreSQL + page preview plan (not executed)

The coordinator must release one bounded preview window before any of these
steps run. The executor records a 30-minute deadline before creating resources;
no retry or extension is implicit.

1. Use one task-owned temporary fixture from the already cached PostgreSQL 17
   image `public.ecr.aws/docker/library/postgres@sha256:7bade6d532592ca8ce7ee32def7399dad2607c4ea5583839fc4352a095a11ea6`.
   Reserve container `a2flow-af11-management-pg17`, database
   `a2flow_af11_management_prt`, role `a2flow_af11_preview`, and one unique
   `/home/admin/OpenSource/.tmp/af11-management-pg-*` socket/data fixture. Keep
   `--network none`, no host TCP publication, bounded resources, and tmpfs
   PGDATA. Do not reuse an unknown database or create a persistent volume.
2. Create those exact temporary PRT database and role names in the reviewed fixture.
   Run the existing explicit asset-store setup and non-overwriting MVP seed for
   namespace `a2flow-mvp-activity-planning`. Then run
   `PostgresDraftRepository.setup()` once as a separately recorded operator
   action. Host startup itself performs neither operation.
3. Before starting a listener, read back the database name, environment marker,
   namespace, and resolved non-empty lists for exactly `SKILL`, `ABILITY`,
   `APPLICATION`, and `WORKFLOW`. Retain no credential or document body in the
   evidence.
4. Prepare a new owner-only management Bearer token under a unique mode-`0700`
   `/home/admin/OpenSource/.tmp/af11-management-secrets-*` directory, with the
   token file mode `0600`. Set browser origin to
   `http://127.0.0.1:14176`. Start this Host as the fixture owner on
   `127.0.0.1:8766` only. Confirm unauthenticated,
   wrong-token, spoofed-identity, and non-loopback requests fail before any
   asset/draft I/O; then confirm the authenticated session reports the fixed PRT
   administrator. Run the Host under a 30-minute terminating supervisor; do not
   leave a listener alive merely because the browser is idle.
5. After the UI owner's `apps/management/web` candidate is integrated and its
   tests pass, build it with the already locked dependencies. Point
   `A2FLOW_MANAGEMENT_STATIC_DIRECTORY` at that exact `dist`; the Host serves UI
   and `/management/*` from one origin. Create SSH tunnel
   `127.0.0.1:14176 -> server 127.0.0.1:8766`, open the login page, and type the
   new preview token once. The UI's existing `credentials: same-origin` requests
   then use only the HttpOnly session cookie and never add `userId`, environment,
   role, or token fields. A `USER` Host is read-only; choose `ADMIN` only for the
   explicitly reviewed draft exercise.
6. In the browser, verify list/detail for all four kinds and an administrator
   draft save/validation/publication-plan flow. The final action must remain
   labelled `PREPARED_NOT_PUBLISHED`; compare immutable asset and serving rows
   before/after to prove no publication occurred. No model call is part of this
   preview.
7. At success, failure, or the deadline, stop the exact Host process first,
   close the local `14176` tunnel, then stop and remove only container
   `a2flow-af11-management-pg17`. Remove only the recorded temporary socket/data
   and secret directories. Prove ports `8766`/`14176`, the container, volumes,
   fixture paths, and token are absent. Main/Git source delivery, PostgreSQL
   evidence, and browser evidence must be reported as separate gates.

Current prerequisites are therefore: coordinator release, the exact cached
PostgreSQL 17 fixture, explicit temporary DB/role/socket values, the reviewed
four-kind seed, explicit draft-schema setup, a newly generated protected token,
and the integrated UI candidate. The cookie bridge supports its same-origin API
client without modifying production authentication interfaces. None of those
runtime actions is performed by this source slice.
