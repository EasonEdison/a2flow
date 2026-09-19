# B-side platform API (accounts / chat / workflows / runs / schedules / notifications)

Fail-closed FastAPI service. Import performs no I/O; `create_app_from_environment`
builds the app from explicit protected configuration only.

Required environment (no defaults; missing values refuse startup):

- `A2FLOW_BSIDE_DATABASE_URL` / `A2FLOW_BSIDE_DATABASE_NAME` — explicit PostgreSQL
  binding; the database is not created or migrated by this service.
- `A2FLOW_BSIDE_PEPPER` — ≥16 chars, server-side password pepper.
- `A2FLOW_BSIDE_SESSION_SECONDS` — cookie/session TTL (60..604800).
- `A2FLOW_BSIDE_BROWSER_ORIGIN` — exact browser origin (loopback or explicit
  public origin). Unsafe methods require the exact Origin header.
- `A2FLOW_BSIDE_RUNTIME_URL` — Runtime control interface base URL.
- `A2FLOW_BSIDE_ENVIRONMENT` — PRT or ONLINE (matches the Runtime environment).
- `A2FLOW_BSIDE_ASSET_NAMESPACE` — asset namespace for the workflow catalog.
- `A2FLOW_BSIDE_VALIDATOR_FACTORY` — trusted validator factory reference.

Identity: sessions resolved from the `a2flow_bside_session` HttpOnly
SameSite=Strict cookie. Client identity headers and all `/api` query parameters
are rejected. All rows are userId-scoped; cross-user access returns 404.

Run/stop/action proxy the reviewed Runtime control routes; ownership is
enforced by the local `run_ownership` table before any call is forwarded
(control ids are the v1 b-side run identity).

Offline tests: `python -m unittest discover -s services/b-side-api/tests`
(no database or Runtime required; fakes are injected).
