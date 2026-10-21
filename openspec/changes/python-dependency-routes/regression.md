# Verification — 2026-10-22

## Behavior and production wiring

- Offline actual generic/attended B and realchat B/Runtime composition: **5 PASS**. External network and database access are blocked; no model or business operation runs. The actual factories construct concrete dependencies.
- Immutable baseline fixtures: all **42 B routes** and **19 Runtime routes**, registration order, methods, response classes/status and full OpenAPI path/request schemas remain equivalent.
- Runtime progress/SSE: **7 PASS**, including bounded send timeout, lease close, observer disconnect and capacity release.
- Delivery targeted regression: **11 PASS**; Chat history **2 PASS**; model factory uses synthetic synchronous/asynchronous MockTransport, never provider keys.
- All nine groups in `scripts/run_core_probes.py --python-probe all` pass: account guard (32 concurrent attempts), outbox (15 invariant scenarios), capability approval (70), native Chat recovery (4), durable Chat (37), route composition (5), Chat write approval (243), Workflow write approval (41), A2UI preflight (38). Real PostgreSQL is disposable; all owned containers/schemas/private files removed.

## Static boundary scope

Expanded gate: **28 files PASS** (14 HTTP, seven persistence/assembly, three Runtime transport, four production/model factory). Existing foundational mypy/Ruff/format: **two files PASS**. Repository: **381 Python files / 107 entry-doc links PASS**, Runtime import boundary and Compose syntax PASS, `git diff --check` PASS.

`scripts/check_python_dependency_types.py` checks explicit lists: strict new HTTP modules and Runtime transport; strict declared types at persistence/production composition with untyped imported legacy calls permitted. It never ignores missing imports, argument/return mismatches or errors in selected modules. Imported legacy module bodies are outside this expansion. Ruff and formatting are checked for the listed files. This is expanded coverage, not whole-repository strict typing.

The probe image uses the pinned quality lock and the existing RPC package's mypy/protobuf/gRPC typing versions, plus the croniter stub. These are development/test tools and do not change production dependencies. The core CI job runs the quality gate and the new composition probe.

## Existing failures and limits

Broader B discovery: **73 cases = 65 PASS, 2 PostgreSQL skips, 4 FAIL + 2 ERROR**. The six failures/errors are identical to baseline: old schedule/run/notification fakes and incomplete InternalRunStart fixture. Runtime HTTP: **12 cases = 10 PASS + 2 identical baseline FAIL** (old timeout-state and stale-reset assertions). Their exact identities are recorded in [inventory](inventory.md); this refactor does not repair or conceal them. No claim of an entirely green repository suite.

No frontend/Java build is needed for this Python-only structural change. No database migration, real provider call, listener, deployment or public business acceptance was performed. Deployed components remain distinct from the source being delivered.
