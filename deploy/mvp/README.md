# Private MVP08 runtime host

This directory assembles the reviewed activity-planning assets, PostgreSQL-backed
Runtime, native LangGraph continuation, DeepSeek flash model and optional static
UI. Importing `deploy.mvp.app` does not start a listener or perform DDL. The
FastAPI lifespan performs idempotent schema setup only when an operator starts the
app.

The host is intentionally single-user and environment-bound. Browser requests
cannot choose `userId`, environment, model, database, namespace or credentials.
The fixed server-side identity is a private-preview boundary, not gateway
authentication or multi-user authorization. Bind only to loopback and reach it
through an SSH tunnel. A public bind or shared-user deployment is outside this
MVP contract.

## Repeatable Docker Compose host

The checked-in `Dockerfile` and `compose.yaml` package the same reviewed Python
sources without publishing a port beyond loopback. The Compose project has two
persistent named volumes: `postgres_data` for all asset and Runtime history, and
`runtime_state` for the model-request counter and bounded structural error log.
Restarting the Runtime container opens the existing database and serves saved
history; it does not start or resume a Workflow.

With the example project name, the deployment candidate is one local image
`a2flow-runtime-private:af09-a`, services `a2flow-private-postgres-1` and
`a2flow-private-runtime-1`, volumes `a2flow-private_postgres_data` and
`a2flow-private_runtime_state`, and host listener `127.0.0.1:8765`. Changing the
project name or host port creates a separate explicit target rather than
reusing an existing preview implicitly.

Prepare an env file outside the repository from `compose.env.example`. Create a
private secret directory outside the repository containing exactly
`postgres_password` and `deepseek_api_key`; do not put secret values in the env
file. The UI path must name an already-built `apps/digital-employee/web/dist`.

The Runtime and seed containers run as the fixed numeric identity
`10001:10001`. Prepare only the exact task-owned files for that identity. One
`postgres_password` source file is mounted into both services: the PostgreSQL
entrypoint begins as container root and can read it, while Runtime reads it as
group `10001`. Set that file to owner `root`, group `10001`, mode `0440` (or an
equivalent exact-file ACL). Set `deepseek_api_key` to owner/group `10001` and
mode `0400`. Give group `10001` read/execute only on the chosen static directory
and read only on its files, for example directories `0750` and files `0640`.
Apply these permissions only to the dedicated secret directory and copied UI
artifact; do not make a shared parent tree world-readable and do not change
global host groups or security policy. The operator must perform and verify
these exact-file permissions before Compose starts; this repository does not
alter host permissions automatically.

Render the final configuration before any build or start:

```bash
docker compose --env-file /absolute/private/a2flow.env \
  -f deploy/mvp/compose.yaml config --quiet
```

The Dockerfile uses the existing exact Python dependency locks. Its Python base
tag and the PostgreSQL image digest are review inputs for an operator build; this
source delivery does not pull or build them automatically.

Start PostgreSQL, run the explicit seed once, then start the Runtime:

```bash
docker compose --env-file /absolute/private/a2flow.env \
  -f deploy/mvp/compose.yaml up -d postgres
docker compose --env-file /absolute/private/a2flow.env \
  -f deploy/mvp/compose.yaml --profile tools run --rm seed
docker compose --env-file /absolute/private/a2flow.env \
  -f deploy/mvp/compose.yaml up -d runtime
```

Running the seed command again returns `NO_CHANGE` for identical content.
Conflicting stored content returns a fixed error and is never overwritten. Seed
is not part of Runtime startup. Use `docker compose stop` for graceful shutdown;
do not use `down -v` when history must be retained.

The default published address is `127.0.0.1:8765`. The fixed trusted user and
environment come from the operator env file and cannot be selected by the
browser. Model calls are admitted through a counter persisted in `runtime_state`;
container restarts retain the count, and every provider client uses zero retries.
The safe error log stores only bounded exception type, allowlisted code and stack
coordinates, never request/model/tool bodies.

## Required host configuration

Set these outside source control:

- `A2FLOW_DATABASE_HOST`, `A2FLOW_DATABASE_PORT`, `A2FLOW_DATABASE_USER` and
  `A2FLOW_POSTGRES_PASSWORD_FILE`: exact PostgreSQL connection supplied by the
  private Compose host. The existing manual listener can still use the legacy
  `A2FLOW_DATABASE_URL` variable.
- `A2FLOW_DATABASE_NAME`: exact database name checked by the asset repository.
- `A2FLOW_ENVIRONMENT`: `PRT` or `ONLINE`; it must match the seeded database.
- `A2FLOW_USER_ID`: fixed private-preview identity.
- `A2FLOW_DEEPSEEK_API_KEY_FILE`: Compose model credential file. The existing
  manual listener can still use the legacy `DEEPSEEK_API_KEY` variable.
- `A2FLOW_ASSET_NAMESPACE`: exact reviewed asset namespace.
- `A2FLOW_MODEL_CALL_LIMIT`, `A2FLOW_MODEL_MAX_TOKENS` and
  `A2FLOW_MODEL_TIMEOUT_SECONDS`: bounded model settings. The call counter file
  and safe diagnostic file must live on the persistent Runtime state volume.
- `A2FLOW_STATIC_DIRECTORY`: optional built UI directory.

The runtime Python path must include the contract, asset-store, registry, Runtime
and activity-planning source roots used by this repository.

## Explicit asset initialization

Generate one reviewed bundle, validate it offline, then name the destination
explicitly. `dry-run` performs database reads but no import write. `apply` is
atomic and never overwrites an existing version.

```bash
mvp_bundle="$(mktemp)"
python -m deploy.mvp.export_bundle \
  --environment "$A2FLOW_ENVIRONMENT" >"$mvp_bundle"

python -m a2flow_asset_store validate \
  --namespace a2flow-mvp-activity-planning \
  --environment "$A2FLOW_ENVIRONMENT" \
  --validator-factory activity_planning_demo:bundle_validator \
  --bundle "$mvp_bundle"

python -m a2flow_asset_store setup \
  --namespace a2flow-mvp-activity-planning \
  --environment "$A2FLOW_ENVIRONMENT" \
  --database "$A2FLOW_DATABASE_NAME" \
  --dsn-env A2FLOW_DATABASE_URL \
  --validator-factory activity_planning_demo:bundle_validator

python -m a2flow_asset_store dry-run \
  --namespace a2flow-mvp-activity-planning \
  --environment "$A2FLOW_ENVIRONMENT" \
  --database "$A2FLOW_DATABASE_NAME" \
  --dsn-env A2FLOW_DATABASE_URL \
  --validator-factory activity_planning_demo:bundle_validator \
  --bundle "$mvp_bundle"

python -m a2flow_asset_store apply \
  --namespace a2flow-mvp-activity-planning \
  --environment "$A2FLOW_ENVIRONMENT" \
  --database "$A2FLOW_DATABASE_NAME" \
  --dsn-env A2FLOW_DATABASE_URL \
  --validator-factory activity_planning_demo:bundle_validator \
  --bundle "$mvp_bundle"
```

Remove only the exact `mktemp` path after the operator has retained any required
audit evidence.

### Additive three-node demo bundle

The independent `activity-package-demo` bundle does not replace the original
activity-planning versions. Export it explicitly, then use the same validate,
setup, dry-run and apply sequence above with the new bundle path:

```bash
python -m deploy.mvp.export_bundle \
  --environment "$A2FLOW_ENVIRONMENT" \
  --demo activity-package >"$mvp_bundle"
```

Its bounded sequential nodes are `choose_plan` (interactive plan selection),
`confirm_schedule` (interactive execution confirmation), and
`show_activity_package` (display-only final package). Each node loads an
independent Skill. Saved Action results are the only confirmed predecessor
facts supplied downstream. The final node persists a real rendered Application
card with no Action and no pause, so a later run-view read can return it after
the Run is terminal.

## Private listener

After asset readback succeeds, start the app on loopback:

```bash
python -m uvicorn deploy.mvp.app:app --host 127.0.0.1 --port 8765
```

From a workstation, use an SSH local-forward to that loopback port. Do not add
identity headers: `GET /runtime/session` reports the server-bound identity.
Starting a Run is the first operation that can call DeepSeek.

This source and its offline tests do not prove a database import, provider call,
listener, deployment or browser regression. Record each of those separately if
an operator authorizes and performs it.

## Prepared one-shot live window

The bounded PG -> seed -> real flash -> waiting Action -> confirmation -> copy
acceptance is specified in mvp08-live-window.md under the owning OpenSpec.
runtime08_mvp_window reuses the accepted isolated-PG cleanup and adds exact
model, time, data and loopback limits. The released window added the exact pinned
Click/Uvicorn versions to the task venv and ran once. Final chain evidence was lost
with the yielded execution handle, so the result is UNCONFIRMED and not READY. Do
not rerun without a new explicit window release. W2 retained an admin-owned 0600
evidence file and finished FAILED at START_REQUEST after four admitted model requests;
no card, Action, copy or terminal Run assertion was reached, while exact cleanup passed.
The old probe did not retain status/code, so the precise backend cause is unavailable.
A source-only follow-up records bounded HTTP status, JSON presence and allowlisted code
without response content. W3 has not been released.
