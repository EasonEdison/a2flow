# Account browser service

Run `python -m deploy.accounts.launcher`. The service listens only on
`127.0.0.1:$A2FLOW_LISTEN_PORT`; port 8780 preserves the Java login proxy target.
Only `/login`, `/logout` and their existing `/private-preview/` aliases exist.
There is no management asset API, static UI, schema initialization or account creation.

Required environment:

- `A2FLOW_ENVIRONMENT`: `PRT` or `ONLINE`.
- `A2FLOW_DATABASE_NAME`, `A2FLOW_DATABASE_USER` and
  `A2FLOW_POSTGRES_PASSWORD_FILE`: existing account database via `/run/postgresql`.
- `A2FLOW_MANAGEMENT_PASSWORD_PEPPER_FILE`: existing shared account pepper file.
- `A2FLOW_MANAGEMENT_BROWSER_ORIGINS`: comma-separated exact browser origins,
  all using the same HTTP/HTTPS scheme.
- `A2FLOW_LISTEN_PORT`: explicit port between 1024 and 65535.

Secret files use `deploy.common.config` ownership, permissions and no-follow checks.
The service reuses B-side `UsersRepository`, `SessionsRepository` and password/token
helpers. Existing users, password hashes and session rows are never rewritten.
M keeps `a2flow_management_session`, HttpOnly, SameSite Strict and 7200-second expiry;
B keeps its existing cookie. The shared session table remains compatible.

Verification: `python -m unittest deploy.accounts.test_account_auth -v` with the
B-side source package on `PYTHONPATH`. These isolated in-memory repository tests
cover browser contracts and shared crypto/session compatibility; deployment and
live PostgreSQL proof are separate checks.


## Shared login and registration admission

Before starting M or B, explicitly apply
`services/b-side-api/src/a2flow_bside/account_guard.sql` to their shared account
PostgreSQL database. The serving factories only check readiness; they never
perform schema migration. A missing table or unavailable admission backend
fails closed. There is no in-memory fallback.

M and B must use the same account database, environment, password pepper and
admission configuration. Login attempts through either surface consume one
shared sliding-window budget. Both valid and invalid credentials consume an
attempt before scrypt; denied requests return 429 and `Retry-After`. Invalid
Origin and malformed proxy headers are rejected before quota admission. Limits
are request-abuse protection, not business authorization or DDoS protection.

| Variable | Default | Meaning |
| --- | --- | --- |
| `A2FLOW_AUTH_LOGIN_WINDOW_SECONDS` | `60` | Shared login sliding window |
| `A2FLOW_AUTH_LOGIN_GLOBAL_LIMIT` | `100` | Login attempts per environment |
| `A2FLOW_AUTH_LOGIN_IP_LIMIT` | `20` | Login attempts per client IP |
| `A2FLOW_AUTH_LOGIN_USERNAME_LIMIT` | `8` | Login attempts per case-folded username |
| `A2FLOW_AUTH_REGISTER_WINDOW_SECONDS` | `3600` | Registration sliding window |
| `A2FLOW_AUTH_REGISTER_GLOBAL_LIMIT` | `30` | Registration attempts per environment |
| `A2FLOW_AUTH_REGISTER_IP_LIMIT` | `5` | Registration attempts per client IP |
| `A2FLOW_AUTH_REGISTER_USERNAME_LIMIT` | `3` | Registration attempts per case-folded username |
| `A2FLOW_REGISTRATION_ENABLED` | `true` | Set `false` to disable B self-registration |
| `A2FLOW_AUTH_TRUSTED_PROXIES` | empty | Comma-separated exact trusted proxy IPs; no CIDR or wildcard |

Positive integer limits/windows accept values from 1 to 86400. Configure both
M and B identically and restart them together after changes. Username lookup
and uniqueness remain unchanged; case folding only affects admission grouping.
Self-hosted installations should explicitly choose registration policy; the
existing deployment retains `true`.

By default only the actual transport peer identifies the caller. If and only
if its IP is explicitly trusted, the guard requires exactly one
`X-A2Flow-Client-IP` header containing one valid IP. Nginx must overwrite this
header with its verified `$remote_addr`; intermediary proxies must preserve
that verified value without accepting arbitrary browser-supplied identity.
`Forwarded` and `X-Forwarded-For` are not read by this guard. Launchers retain
`proxy_headers=False`. The current single-host proxy may explicitly trust
`127.0.0.1,::1`; do not trust an entire external network.

Guard rows contain only environment/action, HMAC-derived address and username
keys, and timestamps. They contain no plaintext passwords, session values,
raw usernames or raw client IPs. Expired rows are deleted on the next admission
for that environment/action; this is opportunistic cleanup, not a background
retention job. Database failures return 503 with a server-generated
`X-Request-ID`; the corresponding log contains only the operation, correlation
identifier and exception type, never exception details or request data.


## Recovery and reproducible verification

See [operator account recovery](../../docs/account-recovery.md) for the explicit
single-administrator transaction, current-pepper requirements and M/B session
revocation. It does not add a Web password-reset flow or recover plaintext passwords.
The [isolated public probe](../../scripts/verify_account_guard.py) requires an
owner-only DSN file and an empty, explicitly named local probe database. It covers
shared quotas, proxy boundaries and synthetic password recovery without contacting
an existing installation or a model.
