# AF-RUNTIME-05 regression evidence

Date: 2026-09-08. Source: the worker candidate containing this record, based on AF05-E1 cee8149; exact fixed SHA is reported to main-brain after commit.
No PostgreSQL/listener/provider/deployment executed in AF05.

## Executed source gates

The final service suite command is the README's PYTHONDONTWRITEBYTECODE/PYTHONPATH command with unittest discovery. Final result: 104 tests in3.460s, 87 PASS and17 SKIP (AF03 nine + AF04 eight opt-in PG cases). Experiment discovery with the same environment passed43/43 in0.768s; its implementation did not change afterward. Earlier assembly-only3/3 and HTTP9/9 are intermediate gates, not added to the final total. Tests explicitly inject synthetic model/business/configuration ports and in-memory persistence, except SQL recording-connection tests. No implicit storage fallback exists.

- Actual HTTPX ASGI requests exercise formal start -> Skill -> interactive wait -> completing Action -> native continuation -> Finalizer -> durable SUCCEEDED.
- Canonical repeated start/restart does not rebuild/dispatch; changed restart payload conflicts; terminal duplicate Action rejects without another executor call.
- Long guarded native node: committed DISPATCHING receipt yields runId while POST is pending; status and stop complete through separate requests; excess execution receives CAPACITY_EXHAUSTED before any receipt is written. Late completion preserves STOPPED.
- Long completing Action: projection sees saved EXECUTING without acquiring its held Action scope; stop returns before business release; late business completion is retained, resumeDelivery remains NOT_REQUESTED, stopped interaction NOT_OPERABLE.
- Actual asyncio request-task cancellation while native work is blocked: cancelled waiter exits, occupied execution slot remains unavailable, control/read/stop still operate, and eventual receipt becomes RETURNED without another factory invocation.
- Separate direct ASGI receive harness delivers http.disconnect before body completion and proves no dispatch. This is not a real socket/proxy disconnect or proof of every ASGI server's shutdown behavior.
- Read deadline expires while injected synchronous projection still blocks. Its capacity remains occupied, new reads fail fast, and independent stop remains available. Eager initialization is exercised without lifespan; invalid/unbounded read deadlines reject.
- Missing context, forged identity headers/body, different owner/environment, wrong run/node/card, stale versions and malformed action input fail without business execution. Stopped card fails RUN_STOPPED.
- Fresh restart yields a new run/thread and current input/version closure while spies forbid old full Run/operation reads.
- False Content-Length + streamed overflow rejects based on actual bytes; exact 64KiB body succeeds and +1 fails. Exact 256KiB response succeeds and +1 fails before sending; validation/exception/oversize private sentinels are absent from error payloads.
- Output failure after a successful start does not cause a repeated control to dispatch. Business TimeoutError is INTERNAL_ERROR, its control remains UNCONFIRMED; duplicate start preserves RUNNING with explicit UNCONFIRMED initial receipt and no liveness claim.
- SQL recording connection: independent READ ONLY REPEATABLE READ transaction, owner/env filters, configured timeouts, safe JSON paths, collection LIMIT101, no explicit row/advisory/AF03 lock or raw result/checkpoint selection; failure closes without reconnect.
- Explicit truncated flags preserve unknown remainder; historical INTERRUPTED does not become native waiting; stopped historical cards remain non-operable.
- AST scan finds no formal production imports of experiments or test fixtures.

## Dependency evidence (AF05-D1)

Before install, importlib.metadata.distributions() enumerated 122 records for 61 unique PEP503-normalized names. lib64 is an alias to lib: resolved metadata path/version was identical for every duplicate; no ambiguity and no environment cleanup was necessary. After install: 128 records, 64 unique names. Every old name/version remains unchanged, including pip22.3.1, DeepAgents0.7.13, LangGraph1.2.11, LangChain1.4.0, core1.6.2, AnyIO4.15.1, HTTPX0.28.1 and Pydantic2.13.5.

The portable original name/version map is af05-installed-before.json (no environment path dump). The resolver constrained every existing distribution; it proposed only these three wheels from official PyPI/files.pythonhosted.org:

| Wheel | Actual bytes | SHA256 verified before install |
| --- | ---: | --- |
| fastapi-0.141.1-py3-none-any.whl | 131954 | bfb91aa2d334c61cb35ba9a116fc123b3d3df31640b801cf57a7a78ec3f603b3 |
| starlette-1.6.0-py3-none-any.whl | 75969 | a86dd39d14bb45f85a3d18525215a9ef0cfd1f192ac793220e72598c90335f0c |
| annotated_doc-0.0.5-py3-none-any.whl | 5302 | 117bac03a25ede5df5440e855b32d556049ca169ead221505badf432fed4b101 |

Total213225 bytes. Download used pip download --no-deps --no-cache-dir with pinned versions. Local bytes were hashed and checked against AF05-D1 before pip install --no-index --no-deps on those exact wheels. No wheel entered Git; no standard extras, Uvicorn, pip/system/SDK update. Post-install pip check: no broken requirements. FastAPI/Starlette/AnyIO/DeepAgents/LangGraph imports PASS. Main-brain independently checked current versions, resolved duplicates, pip check and all three wheel hashes.

Reproducible version comparison: enumerate distributions, normalize Name by lowercasing and replacing runs of hyphen/underscore/dot with hyphen, assert all duplicate (version, resolved metadata path) pairs match; compare the original JSON's normalized map with current versions; assert the only extra names are fastapi0.141.1, starlette1.6.0, annotated-doc0.0.5. The installation script performed the complete old-version diff, and a separate normalized-name/read-path check confirmed no collisions.

## Limits

The new PG projection's SQL syntax/visibility/lock timing has only recording-connection evidence, not a real database run. Existing AF03/AF04 PG histories remain their original fixed-source evidence; their default skips are not new passes. No network listener, real provider, live business API, full Workflow compiler, public auth product, durable replay, distributed service load test or automatic recovery was exercised.

## Exact executed commands

From the exclusive worker, using the existing Python3.11 project venv:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=packages/contracts/src:services/agent-workflow-runtime/src:services/skill-registry/src:experiments/runtime-phase1:experiments/runtime-phase1/tests \
/home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python \
  -m unittest discover -s services/agent-workflow-runtime/tests -q

PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=packages/contracts/src:services/agent-workflow-runtime/src:services/skill-registry/src:experiments/runtime-phase1:experiments/runtime-phase1/tests \
/home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python \
  -m unittest discover -s experiments/runtime-phase1/tests -v
```

The final source tests preceded documentation-only edits. No AF05 PG window was run.

Submission checks: fetch/merge origin/main already up to date at cee8149; git diff --check PASS; gitleaks --redact on the three owned directories reported no leaks; all owned files admin-owned; internal-source marker scan returned no matches. Exact21-file owned candidate; no root/shared-contract/other-domain edits or tracked wheels.
