# Getting started / 开始使用

There are three different levels of reproduction. Do not mistake a successful build or synthetic preview for live workflow execution.

| Level | Requirements | What it establishes |
| --- | --- | --- |
| Source checks | Git, Python 3.11+, Node 22.12+, npm; JDK 17/Maven for Java | Syntax, selected boundaries, types and frontend/Java compilation |
| Local fixture | Built B frontend, no account or model key | Synthetic workflow card/state rendering only |
| Real product | Provisioned PostgreSQL, accounts, published assets, model config, RPC targets/certificates and services | Actual authenticated model/tool execution; requires separate acceptance |

## 1. Check a clone

```sh
git clone https://github.com/EasonEdison/a2flow.git
cd a2flow
python3 scripts/check_repository.py
git diff --check
```

This dependency-free script parses tracked Python source without importing it or opening a database, checks current documentation links, validates frontend manifests, and rejects direct product/content imports in the generic Runtime. It does not establish semantic correctness or complete architecture isolation.

Optional existing strict Python subset (two DTO modules, not whole-repository coverage):

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-quality.lock
make quality-python PYTHON=python
```

## 2. Build and view the local B fixture

From the repository root:

```sh
cd apps/digital-employee/web
npm ci --ignore-scripts --no-audit --no-fund
npm run build
npm run preview
```

Open `http://127.0.0.1:4173/employee/?preview=fixture`. The `/employee/` prefix and `preview=fixture` parameter are both required. The page labels itself as simulated and supports running, waiting, completed, unconfirmed and stopped views. Submitting its card only changes local fixture state; refresh resets it. This is an older focused workflow-card preview, not the complete authenticated workspace, personal-workflow builder or activity rail.

Use Ctrl+C to stop the local server. It binds loopback, not a public interface.

## 3. Build the current management UI and Java control plane

From the repository root:

```sh
(cd services/management-java/frontend && npm ci --ignore-scripts --no-audit --no-fund && npm run build)
mvn -f services/management-java/pom.xml -DskipTests compile
```

Use JDK 17. `apps/management/web` is a historical frontend and is not the current management build. The current UI needs its same-origin Java API and authenticated account to show real assets; a standalone dev server is not an API fixture.

## 4. Validate deployment syntax without starting services

With Docker Compose v2 installed:

```sh
python3 scripts/check_compose.py
```

The script creates temporary empty environment files and placeholder paths, runs `docker compose config --quiet` for the self-hosted, Java operator, Python execution and combined override definitions, then removes only its temporary directory. It does not contact a database, create containers, pull images, provision accounts or print private configuration. This checks syntax only, not image existence or service readiness.

## 5. Plan a real installation

The current [Java deployment guide](../deploy/java-management/README.zh-CN.md) and [Python execution guide](../deploy/python-execution/README.zh-CN.md) describe an operator-managed topology. They assume an existing PostgreSQL socket volume, account/runtime stores and an image/dependency chain. The older real-chat/attended deployments are assembly history, not interchangeable current installers.

Use the separate [self-hosting guide](../deploy/selfhost/README.md) for a fresh database/bootstrap path, configuration inventory and public image build chain. Its explicit initializer refuses to adopt unrelated existing database names and does not reset an existing administrator. Do not run historical `prepare.py` against existing databases as a quick-start shortcut. Current evidence is recorded in [foundations acceptance](../openspec/changes/production-foundations/regression.md).

For a real demonstration, provision the exact trusted browser origin, HTTPS for password login, accounts/roles, PRT assets, model access and mTLS RPC targets. Keep all secret files outside Git. A model response alone is insufficient: inspect the saved run, interaction and business receipt records. There are no default admin credentials.

## Troubleshooting

- Both current frontend directories pin the public npm registry in `.npmrc`; private developer registry settings are not installation prerequisites.
- Node version error: use Node 22.12+ (CI uses Node 22); install with the committed lock file via `npm ci`.
- Login screen instead of a fixture: check `/employee/?preview=fixture` exactly.
- Management UI loads but requests fail: it has no standalone fake API; check the authenticated backend separately.
- Compose reports a missing variable: use the supplied syntax-check script for local validation; do not paste real secrets into issue output.
- Missing model/RPC configuration: configuration failure is explicit; the platform does not silently switch to a simulated model or business service.
