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
