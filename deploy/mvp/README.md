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

## Required host configuration

Set these outside source control:

- `A2FLOW_DATABASE_URL`: exact PostgreSQL DSN.
- `A2FLOW_DATABASE_NAME`: exact database name checked by the asset repository.
- `A2FLOW_ENVIRONMENT`: `PRT` or `ONLINE`; it must match the seeded database.
- `A2FLOW_USER_ID`: fixed private-preview identity.
- `DEEPSEEK_API_KEY`: model credential.
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
