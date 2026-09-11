# AF-MVP-08-LIVE-W1 controlled window

Status: RAN ONCE / LIVE RESULT UNCONFIRMED. Main released the exact window and the
single process exited within its budget, but the caller lost the yielded execution
handle after retaining only the first output line. Final test output, exit status and
model/card/node/Run evidence are unavailable, so this is not a successful chain proof.

## One bounded objective

Prove exactly one source-accepted activity-planning path:

1. create an isolated PostgreSQL 17.11 instance;
2. initialize the asset and Runtime schemas and atomically seed/read back the seven
   accepted PRT assets in namespace `a2flow-mvp-activity-planning`;
3. bind the Runtime only to `mvp08-live-user` / `PRT` / database `runtime_probe`;
4. start the ASGI app on `127.0.0.1:18765` only;
5. issue one start request using a fixed 12-person, 120000-minor-unit activity brief;
6. observe the committed waiting card, choose its first saved option, and issue one
   node-bound `confirm_activity` Action;
7. require the plan and copy nodes plus the Run to reach `SUCCEEDED`, with the saved
   selected option and one non-empty copy result.

This does not prove browser rendering, refresh UX, gateway authentication, multi-user
authorization, deployment, production data, arbitrary Workflow shapes, or retries.

## Exact owned resources and data

- container: `a2flow-mvp08-pg`
- volume: `a2flow-mvp08-pgdata`
- private directory: `/home/admin/OpenSource/.tmp/a2flow-mvp08-live`
- Docker label/owner marker: `a2flow.owner=oss-agent-workflow-runtime-mvp08`
- PostgreSQL image: the existing AF03/AF04 pinned linux/amd64 PostgreSQL 17.11 digest
- container network: `none`; published ports: none; socket only inside the admin-owned
  private directory
- listener: host process `127.0.0.1:18765`; any wildcard/public bind is forbidden
- seeded data: only the seven accepted demo assets and this one synthetic acceptance
  Run/Interaction/view/checkpoint set in the disposable volume

The container, volume, private directory, generated PostgreSQL credentials and an image
pulled only by this window are cleanup-owned. The existing model-key file is not owned by
the window and must never be deleted or changed by cleanup.

## Credential and model budget

The model secret is never a CLI value and direct `DEEPSEEK_API_KEY` inheritance is
rejected. Main must provide only `A2FLOW_MVP08_MODEL_KEY_FILE`, pointing at an absolute,
non-symlink, admin-owned regular file with mode 0600 and size 1-512 bytes. The child reads
it once, supplies it through `SecretStr`, and never writes or prints it. Failure output is
fixed and redacted; request/response bodies and generated text are not acceptance output.

The provider destination is exactly HTTPS `api.deepseek.com/.../chat/completions`, model
`deepseek-v4-flash`. A transport guard enforces at most six outbound model requests. Each
has `max_tokens=2048`, `thinking=enabled`, `reasoning_effort=low`, a 20-second SDK timeout
and zero retries. Therefore the configured output ceiling is 12288 tokens for the window.
The start HTTP wait is at most 100 seconds, the Action wait at most 60 seconds, and the
outer owned-process window stops at 300 seconds.

Resource stops are inherited from the accepted PG window: less than 512 MiB available,
more than 128 MiB swap growth, or more than 256 MiB task-volume data. The container remains
256 MiB/no-extra-swap, 0.5 CPU, pids 128 and shm 32 MiB.

## Dependency and exact entry

The released dependency stage verified the two official pure-wheel hashes, then added
only `uvicorn==0.52.4` and `click==8.3.1` to the task venv. Existing `h11==0.16.0`
was unchanged and `pip check` passed. No system package, pip version or prior Python
distribution was intentionally changed.

Main fixed source SHA `1881855eb4650e7d08f57fbe3bd8e3b647759d0f`, authorized the
task-venv additions and supplied the managed key-file path. The command below records
the released entry; it must not be run again under this one-window release:

```bash
/home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python -m pip install \
  --no-deps --requirement deploy/mvp/listener-requirements.lock

export A2FLOW_MVP08_MODEL_KEY_FILE=/absolute/admin-owned/0600/model-key-file
PYTHONPATH=experiments/runtime-phase1 \
  /home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python \
  -m runtime_phase1.runtime08_mvp_window \
  --authorized-window --expected-source-sha <main-released-40-char-sha>
```

The flag is not authorization. Run once only. A failure is terminal for the window: do not
retry the model, Action, seed, or full command. The shared `finally` stops/reaps the owned
process group, scans PostgreSQL logs for the generated PG passwords without printing logs,
and attempts exact resource cleanup even if process or log checks fail.

`--cleanup` is only for an independently verified residual of these exact owned targets.
It validates label/marker ownership before deletion. If ownership or inspection is unknown,
stop and escalate; never broaden the cleanup target.

## Prepared offline evidence

- the new modules compile without importing Uvicorn or performing I/O;
- the shared AF03/AF04 safety tests and MVP08 preparation tests run without Docker, PG,
  credentials, listener, provider or package installation;
- the live acceptance remains opt-in and skipped outside the exact window marker;
- provider destination/token/call guards have offline request-shape tests.

The released run is consumed. A second attempt requires a new explicit window; cleanup
success must not be used to infer model, card, node or Run success.

W1 prepared SHA256 values:

- shared PG safety: 902d8c0b551b6d550ee4d5013e686248cec72712afd023b42e8b23a330cbcb6d
- MVP08 entry: 6ff87388cd07c2d3f302e936eeb8390aa06353587a8f7be9b93b294810840e89
- live probe: 62a4db1020af63359cb1e03c03fd6621cf5a4f028d1534dcf99e77185c20b868
- offline window test: 05c6c3cd7b5ce18a091c39b3a2b588eeb109a190c7fc72da2017a295f1fd9613
- opt-in acceptance test: 6f765b3581258079c08fd954a90bf57c509a96b665a093b81ff05e5501719a83
- listener lock: 5b79fcbe1e59b0197945b4fef36d41d5bc6f5310c3a7447546638e43d2b6b8ce

## Actual one-shot result

- Dependency result: PASS. Official wheel SHA256 values matched the released values;
  `pip check` and final Click/H11/Uvicorn versions passed. A first comparison command
  stopped after installation because `comm` used inconsistent locales; the packages
  were not downloaded or installed again, and the corrected check was read-only.
- Entry result: the first retained line confirmed source SHA `1881855...` and that the
  key file had only been metadata-verified at entry. The owned window and live-test
  child were observed running with the PG container on network `none` and no ports.
- Evidence capture failure: the tool call did not retain the yielded exec session ID.
  After the process exited, final unittest output/exit code and the disposable database
  were unavailable. Actual model call count, saved card, node status and Run status are
  therefore UNKNOWN, not failed or passed facts.
- Postflight: owned process, container, volume, private directory and listener were
  absent; the pinned image was absent; Git remained clean at `1881855...`; the model
  key remained admin-owned mode 0600 with 36 bytes; `pip check` passed.
- No rerun was performed. Runtime and browser readiness remain NO READY.

## W2 durable evidence preparation

W2 has not been released or run. Source preparation only adds an append-only,
task-owned evidence target outside disposable PostgreSQL cleanup:

- exact file: `/home/admin/OpenSource/.evidence/oss-agent-workflow-runtime/af-mvp-08-live-w2.jsonl`;
- parent directories must be admin-owned mode 0700; the file is newly created with
  `O_EXCL|O_NOFOLLOW`, admin ownership and mode 0600, so prior evidence is never
  overwritten;
- bounded JSONL records cover `ENTRY`, `LIVE_STAGE`, `LIVE_RESULT`, `CHILD_EXIT`,
  `PG_RESULT`, `CLEANUP_RESULT` and `WINDOW_RESULT`;
- records contain only fixed stages, safe result fields, real model-call counts and
  bounded resource metrics. They never contain the key, DSN, request/response body,
  model text, run/card identifiers or exception messages;
- evidence persistence does not relax cleanup. Exact process, container, volume,
  private-directory and listener cleanup still runs in `finally`, and its outcome is
  independently recorded.

W2 evidence-capture SHA256 values:

- PG entry/cleanup: 2a200afe4dd17c0ed6323e21b1062e62b9937f7eec05389f0b0a9be8c50f6291
- MVP08 entry: 4ea85adb55c57930c23296eec5f9403a9b18478155020a0bb41c27fd80c2732a
- live probe: 69a371cfa9d438d9ab4ea8c7612cdab436c043e15756d5705be15749581b0146
- focused failure/cleanup test: 58f39b06f68ec57da82ad8922239c4a19b0fca733c2af34dbdc11ae09429bfbe

A future released command must use the final reviewed source SHA in both the Git
preflight and `--expected-source-sha`. The caller must retain and print the complete
execution result object, including `session_id`, then poll that exact session until a
terminal exit. Losing the handle is no longer a reason to rerun: the 0600 evidence
file remains available for a separate metadata-checked, read-only collection step.
