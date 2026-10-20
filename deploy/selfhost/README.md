# Self hosting from an empty installation

This separate installation does not import an existing A2Flow database or reuse its
volumes. Current scope is one host, PRT execution, Java management, Python accounts,
Chat/Workflow, execution/content services, management Agent and scheduled work.
ONLINE receives a separate empty publication database, not an ONLINE execution claim.

## Requirements and build

Use Docker Engine/Compose v2 or Docker Desktop, Python 3.11+, OpenSSL, and enough disk
for Node/JDK/Python layers (plan at least 12 GB) and at least 4 GB memory for builds.
Do not build Java/npm on a low-memory serving host; build the same reviewed source
elsewhere and import the resulting images. No private SDK image is required.

From the repository root, generate a **new** owner-only directory outside Git:

```sh
python3 deploy/selfhost/configure.py \
  --directory "$HOME/.a2flow/selfhost-one" \
  --origin http://127.0.0.1:18080 --admin-user myadmin
```

The command prompts without echo for an explicit administrator password and DeepSeek
API key. Automation may use `--admin-password-file` and `--model-key-file`, never
plaintext command arguments. No password defaults exist; only the administrator
hash is retained. Keep the private directory and its CA offline backup secure.
Configuration generation refuses an existing directory and does not touch databases.
For public access configure the final exact HTTPS origin instead. The host mapping
remains loopback; configure your own TLS reverse proxy separately.

```sh
SELFHOST_ENV="$HOME/.a2flow/selfhost-one/compose.env"
docker compose --env-file "$SELFHOST_ENV" -f deploy/selfhost/compose.yaml config --quiet
docker compose --env-file "$SELFHOST_ENV" -f deploy/selfhost/compose.yaml build --pull gateway management bside
```

Images are built from public Node 22, Maven/Temurin 17, Python 3.11 and nginx sources.
The Python image installs the repository SDK/model/HTTP locks plus declared RPC,
content and scheduling dependencies. Base image tags and some transitive constraints
are not immutable digests; retain the resulting image IDs with your source revision.

## Explicit initialization (no sample assets are seeded)

```sh
docker compose --env-file "$SELFHOST_ENV" -f deploy/selfhost/compose.yaml up -d postgres gateway
docker compose --env-file "$SELFHOST_ENV" -f deploy/selfhost/compose.yaml --profile tools run --rm initialize databases
docker compose --env-file "$SELFHOST_ENV" -f deploy/selfhost/compose.yaml --profile tools run --rm management-migrate
docker compose --env-file "$SELFHOST_ENV" -f deploy/selfhost/compose.yaml --profile tools run --rm initialize schemas
docker compose --env-file "$SELFHOST_ENV" -f deploy/selfhost/compose.yaml up -d --no-build
```

Database names and roles are prefixed by `--prefix` (default `a2flow_selfhost`); the
prefix also names the Compose project. Bootstrap refuses pre-existing unmanaged
names, records the installation identity, checks SQL digests, and preserves existing
accounts/assets on repetition. A partial configuration generation requires inspection
and a new directory; never delete an installed configuration to "retry". Repeating
the three initialization commands for the **same** installation is a verification,
not password recovery. A changed migration digest requires an explicit migration.

Normal restart uses `docker compose ... restart` or `stop` followed by `up -d`.
No command automatically publishes assets, starts a workflow or replays business work.
Runtime's existing idempotent table-readiness setup is retained. Named PostgreSQL and
Redis volumes retain records. `down -v` destroys data and is not a restart command.

## First real use

1. Open `/login`, sign in with the explicit administrator, and open `/management`.
2. Open `/employee/` and sign into its separate B session with the same account.
3. For the smallest model-backed path, ask management chat to create two Skills:
   collect a missing name through a temporary interaction, then summarize the
   submitted name; create a sequential Workflow and publish it to PRT. This uses
   normal management tools and does not require a preconfigured business catalog.
4. Optionally open `/examples/reading-content/import.html` to publish the full
   content example. Keep official catalog synchronization enabled, load its
   bundled descriptor, choose target `content` and specialist `101`, then review
   and explicitly submit. Its real capability dry-runs create example content
   records in this new installation. Once its project catalog is published,
   `/examples/people-selection/import.html` can add the read-only synthetic people
   example. Neither importer writes publication tables directly.
5. Run the published workflow in B. Missing
   input should create a temporary interaction. Submit once and inspect the saved
   result and history after refresh/restart. Model access is required for this step.

The content example has no connection to a company's production APIs. Add adapters
through supported management contracts; generated assets do not deploy new services.

## Configuration inventory

| Configuration | Owner and purpose |
| --- | --- |
| `compose.env` | Nonsecret project, UID/GID, absolute directory, host port and image tag |
| `bootstrap/config.json` | Installation identity, generated DB role credentials and initial admin hash; initializer only |
| `management/java.env`, `management.json` | JDBC/publication/readonly-account access, port, origins, management Agent/RPC targets |
| `accounts/config.json` | Shared account DB, pepper, trusted origins and auth admission |
| `bside/config.json` | Real Chat host, sessions, runtime endpoint and mTLS execution target |
| `runtime/config.json` | Real Workflow host, asset namespace and mTLS target |
| `execution/config.json`, `targets.json`, `*.dsn` | Readonly release/material access and content RPC target |
| `content/config.json`, `content.dsn` | Isolated content DB and mTLS RPC server |
| `management-agent/config.json`, `agent.dsn` | Dedicated management history schema and grant-bound Java tools |
| `scheduler/config.json` | Persistent PG queue, Redis references and authenticated internal B endpoint |
| Per-service `*.pem`, model/pepper files | Only those service mounts; CA signing key remains outside runtime mounts |

Registration is disabled by default; `--registration-enabled` opts in at initial
configuration. M/B use the same admission store and pepper. The gateway overwrites
`X-A2Flow-Client-IP` from its actual peer and removes generic forwarded headers.
An external TLS proxy must explicitly establish a trusted real-IP chain: pass
`--trusted-edge-ip EXACT_PEER_IP` when generating the configuration (repeat for
explicit known peers). This enables nginx real-IP parsing only for those exact
addresses, before overwriting the backend header. Discover the actual Docker/gateway
peer address; do not trust an entire Docker CIDR or an arbitrary client. Do not
forward arbitrary client-supplied identity or IP headers. Without that chain several
clients can share a proxy IP admission budget. The gateway never publishes internal
`/api/internal/` calls, PostgreSQL, Redis or gRPC to the host.

To replace the model credential, write the new key through a protected file operation
to `bside/model_key`, `runtime/model_key` and `management-agent/model_key`, preserving
owner and mode 0400. Restart only those services; never rerun bootstrap for key rotation.
Do not use an invalid placeholder key as evidence of a model-backed run.

mTLS server/client certificates expire after one year. Rotate through a reviewed
private configuration change; service rollback does not roll back completed writes.
The private CA is installation-specific and is not added to the host trust store.

The explicit administrator is account `user_id=1`. The configured specialist / digital employee `101` is an asset classification identity, not an account or login. Bootstrap creates the administrator independently and never assumes a pre-existing user. Administrator names use 3–32 ASCII letters, digits, underscores or hyphens; passwords use 8–256 characters, matching B-side login limits.
