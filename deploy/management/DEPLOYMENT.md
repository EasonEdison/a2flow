# Persistent private PRT management deployment

This package runs the protected management Host and a new PostgreSQL 17 data
volume without a public port. PostgreSQL has `network_mode: none`, disables TCP,
and shares only its Unix socket volume. The Host uses host networking solely so
Uvicorn can bind `127.0.0.1:8766` and the existing ASGI loopback check continues
to see a loopback server address. No provider/Runtime service is packaged.

Build `apps/management/web/dist` with its lockfile before Compose. Copy
`compose.env.example` outside the repository and set absolute artifact/secret
paths. Create three fresh files: identical random database passwords in
`postgres_password` (numeric owner/group `999:999`, mode `0400`) and
`management_postgres_password` (the configured management UID/GID, mode
`0400`), plus a distinct 32-byte-or-longer printable `management_auth_token`
(management UID/GID, mode `0400`). Keep the directory owner-only. Do not print
their values or put a DSN in the env file.

Render and inspect without starting anything:

```bash
docker compose --env-file /absolute/private/management.env \
  -f deploy/management/compose.yaml --profile tools config --quiet
```

After source review/integration, start the new PRT database, explicitly seed and
initialize schemas once, then start the Host:

```bash
docker compose --env-file /absolute/private/management.env \
  -f deploy/management/compose.yaml up -d postgres
docker compose --env-file /absolute/private/management.env \
  -f deploy/management/compose.yaml --profile tools run --rm initialize
docker compose --env-file /absolute/private/management.env \
  -f deploy/management/compose.yaml up -d management
```

Use an SSH tunnel from local `127.0.0.1:14177` to server
`127.0.0.1:8766`. Host restart invalidates browser sessions but preserves the
database. Stop without deleting history:

```bash
docker compose --env-file /absolute/private/management.env \
  -f deploy/management/compose.yaml stop management postgres
```

For an image rollback, restore the prior reviewed image tag in the private env
file and run `up -d management`; do not run `down -v`. ONLINE is deliberately
unsupported here and requires a separate project, database, data volume,
secrets, and review.
