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

Publication preparation is not publication. Its response always includes
`status: PREPARED_NOT_PUBLISHED` and `published: false`. This slice has no
endpoint that mutates immutable asset versions or serving state.

Bodies are limited to 1 MiB and responses to 2 MiB. Unknown fields, query
parameters, oversized keys, malformed domain identifiers, and invalid target
environment/channel combinations fail with a bounded JSON error code. Error
responses never contain draft content, credentials, connection strings, or
exception text.

No listener starts on import. The existing hash-pinned FastAPI/Starlette runtime
dependencies are reused; this package does not install dependencies itself.
