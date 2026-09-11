# AF-RUNTIME-04 PG window candidate

Status: W1_COMPLETED_ONCE_ACCEPTED_BY_MAIN; DOCUMENT_REVIEW_PENDING; window closed, no rerun authority.
Actual W1 source: 998b4d9f8411a8e09b88abfb665adb330db15e9f.
Runtime source 6ee09e3d67118048489c515b03741723dd552ef5 has passed main-brain's
independent source/offline review. This document and its scripts are an additional
worker commit; use the exact final worker SHA in the coordinator receipt.
No server-main integration or GitHub synchronization follows from this preparation.

## Safety reuse and exact targets

The AF04 entry calls the already-reviewed AF03 safety implementation through
an immutable WindowSpec argument. There is no second cleanup implementation,
global target mutation, SDK modification or new dependency. AF03 no-argument
defaults remain unchanged and its seven injected-fault tests passed again.

- Container: a2flow-runtime04-pg
- Volume: a2flow-runtime04-pgdata
- Private directory: /home/admin/OpenSource/.tmp/af-runtime-04-pg
- Label/owner: a2flow.owner=oss-agent-workflow-runtime-af04
- Environment namespace: A2FLOW_RUNTIME04 (window marker/socket/password-file).
- Image: public.ecr.aws/docker/library/postgres@sha256:7bade6d532592ca8ce7ee32def7399dad2607c4ea5583839fc4352a095a11ea6
- Expected PG: 17.11 linux/amd64; existing AF03 ECR image source, not a new mirror.
- Only admin executes; all targets must be absent before start.
- AF03 resources and its closed W1 are neither used nor reauthorized.

Budget unchanged from the reviewed window: 15 minutes including preparation,
256 MiB PG memory with no additional swap, 0.5 CPU, 128 pids, 32 MiB shm,
32 MiB shared_buffers, role connection hard limit 8/server max_connections 16.
No network, no published ports, Unix socket only behind an admin-only 0700
parent. Start requires available memory >=768 MiB; stop thresholds are <512 MiB
available, >128 MiB swap growth, >1 GiB sampled data size or 900 seconds.
At most two test children run concurrently, plus the unittest coordinator and
one observer thread; Python processes are not falsely claimed to be covered by
the PG container cgroup. Host memory/swap budget applies to the entire window.

Preserved mechanisms: exact absence-vs-UNKNOWN inspection; SCRAM/NOLOGIN bootstrap;
600-mode secret files; unique process group/session marker and admin ownership;
stop/log-check/cleanup nested finally; container log plaintext checks return only
PASS/FAIL; exact socket-subtree privileged deletion only after container removal;
delete only this container/volume/private directory, and a newly pulled image
only if Docker permits non-forced removal. No secure erase claim. Unrelated
resources and an existing/shared image remain untouched.

The entry additionally requires a 40-character expected source SHA, exact HEAD
match and a clean worker before resource setup, then verifies them again after
shared finally cleanup. Merely supplying --authorized-window is not permission.

## Source hashes

- experiments/runtime-phase1/runtime_phase1/runtime04_pg_window.py
  SHA256: a7d392d516598e3db854c7aaad653d0ff6d1ca0bcaf2690003b919d63b3f5c0a
- experiments/runtime-phase1/runtime_phase1/runtime03_pg_window.py
  SHA256: 0456a0b29ead9644d6ca6d3e5f2f0ba552286450d3f6b57a1365a276d7bc107e
- services/agent-workflow-runtime/tests/pg_lifecycle_worker.py
  SHA256: bf36fc8edf3e17e99ad981fb2e780c91b9cfe0625f164355bd784a229b3e7f42
- services/agent-workflow-runtime/tests/test_postgres_lifecycle_integration.py
  SHA256: 1f47e79da9e3b0bf8f39c598df2877fbce3bfb930af8f25228e8ce14a72bf331

The entry hash alone is insufficient: review the shared safety module and both
process-test files from the same fixed source commit.

## Historical W1 command — the released window is now closed

As admin, from /home/admin/OpenSource/repos/.parallel/oss-agent-workflow-runtime/platform:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=experiments/runtime-phase1 /home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python -m runtime_phase1.runtime04_pg_window --authorized-window --expected-source-sha 998b4d9f8411a8e09b88abfb665adb330db15e9f
```

This exact command ran once under the W1 release. It is not standing permission to run it again.
The --cleanup variant selects only AF04 exact targets and is for a separately
authorized cleanup if needed; ordinary execution already performs cleanup in finally.

## Eight reviewed PostgreSQL cases (all passed the single W1)

1. No-card run exists; wrong owner/environment stop rejects; two separate processes
   read the same canonical STOP result and durable STOPPED state.
2. A long completing confirm_route_choice Action uses a third connection to see committed AF03 EXECUTING and AF04
   IN_FLIGHT before its executor event. Another process accepts STOP while that
   Action still holds its AF03 session. Release the old executor; save actual
   business success and interactionCompleted=true, COMPLETED card/RETURNED fact,
   resumeConsumed=false and resumeStatus=NOT_REQUESTED. Actual native-resume,
   Finalizer and guarded successor counters must each stay zero. The positive
   case proves all three counters reach one when there is no stop.
3. Release independent stop/node processes at a PG event barrier. Either admission
   may win; any accepted node fact must have pre-STOP revision 0 and a saved late
   result. No post-STOP process gains a new dispatch. No forced claim that this
   sampled race covers every interleaving.
4. Release independent STOP/conditional-success processes. Exactly one committed
   terminal state wins: STOPPED rejects success; SUCCEEDED rejects a late stop.
5. Start a real synchronous PostgresSaver Skill/interaction, exit the process,
   then stop. New processes reject the old card and raw native Command. A saver
   read spy rejects old checkpoint access before graph progression. Old record
   digests remain unchanged and executor count remains zero.
6. Keep both an old successful non-completing Action and an old UNCONFIRMED fact,
   then STOP and corrupt the old Run input/versions. Each restart child records
   its own ready event before runner.start; the parent waits for both and then
   releases the shared PG barrier. This is a sampled competition, not proof of
   every interleaving. The two processes use only narrow old identity projection, invoke one fresh factory, create new
   run/thread/interaction and resolve current input/v2 config. Old Run/fact/
   interaction/node/checkpoint reads throw in this worker. Conflict payload
   rejects; the new run performs its normal Action even with the same control ID
   as the old run. Old/new executor total must be 2, not cross-run suppression.
7. Positive cross-process Skill→native wait→Action→native resume→Finalizer
   reaches SUCCEEDED with Skill/executor once using the actual synchronous saver.
8. Deterministically admit a real native node, block its actual handler, stop
   from another process, then release the handler. Its actual result remains
   RETURNED and the run remains STOPPED.

All counters and barriers live in the isolated PostgreSQL probe table, not
process-local memory. Synthetic model and business ports only. No recovery,
takeover, compensation, production business API or async execution is introduced.
Each child emits only typed safe JSON and never arbitrary exception text.
The 5 ms pg_stat_activity observer includes itself; observed peak is not an
absolute transient maximum. Teardown checks runtime sessions=0/advisory locks=0
before exact finally cleanup, followed by independent target/port readback.

## Executed preparation evidence (offline only)

- AF04 --help: PASS; no resource setup.
- Experiment suite: 43 tests PASS in 0.554s, including AF03's seven and AF04's
  five offline safety tests. Exact-spec propagation, failed cleanup path, wrong/
  dirty/missing fixed source and CLI routing were exercised using injected fakes.
- Service full scan before fixture correction: 78 total, 61 PASS, 1 fixture error,
  16 PG SKIP (3.547s). The error was mismatched definition names in the memory-only
  restart harness, not a production bypass; corrected the fixture binding and
  reran that exact case: 1 PASS in 0.101s. Earlier missing conninfo stub was also
  corrected; no PG credential was added to make the memory test pass.
- Additional old-PG-read spy test passed; eight AF04 PG cases safely skipped in
  offline discovery. The new deterministic node case remains NOT RUN.
- The three added harness tests pass across their respective focused runs.
  No claim that the latest entire service suite was re-run after these final
  test-only additions. The implementation source remains unchanged from 6ee09e3.
- git diff --check and outgoing secret/scope gates are required before committing.

Only main-brain may approve the incremental code/hash and issue a new single-
executor window. Failures within a real window stop and clean up; no automatic
retry or in-window source modification is authorized by this proposal.

## Incremental review corrections after 46a9f50

- The long Action now exercises a completing Action, not save_choice. Saved
  completion truth and zero actual continuation/Finalizer/successor counts are
  asserted separately; NOT_REQUESTED alone is not accepted as stop evidence.
- A real guarded native successor was added to the probe graph after the Deep
  Agent. The actual continuation adapter and terminal guard record independent
  PostgreSQL counters; the memory positive harness verifies each counter is 1.
- setUp registers addCleanup before creating the first allocate child. Every
  registered exact Popen gets terminate, bounded communicate, then kill/reap
  on timeout/error. One failure is retained but cannot skip later children.
  Non-timeout fatal wait errors are preserved after cleanup, not swallowed.
  The existing outer owned-process-group finally remains unchanged.
- Two restart children must each reach a distinct ready barrier before the
  parent release. Different barrier slots do not enter the canonical control
  payload. No business/recovery behavior or additional PG case was introduced.
- Six focused SDK-harness/child-cleanup tests PASS (0.192s). After adding the
  fatal-wait preservation subcase, the exact changed cleanup test PASS and all
  eight opt-in PG tests SKIP. No shared window safety code or Runtime src changed.
- Entry/shared safety hashes are unchanged; worker/integration-test hashes above
  replace the prior two values. Expected source SHA must be the new approved tip.

Main-brain independently verified exact resource absence, original pause image
retention, unchanged source hashes and clean HEAD, and accepted W1's bounded
result. Evidence documentation review and source integration remain separate.

## Actual W1 result

8/8 PASS in 111.491s, exit=0, on fixed source
998b4d9f8411a8e09b88abfb665adb330db15e9f. Script elapsed before finally cleanup
was 130.26s including pull/preparation. PG 17.11; observed peak connections 5
(5ms, includes observer), min available 1036340 KiB, swap growth 0,
data high-water 50112 KiB. Runtime sessions 0/advisory locks 0; published ports {}.
Credential log check PASS. Exact container/volume/private directory and the
newly pulled image were removed; independent readback confirmed absence and
no 5432 listener. Four source hashes and clean HEAD remained unchanged until
after cleanup/readback. Full assertion evidence is in regression.md.

Main-brain independently verified exact resource absence, original pause image
retention, unchanged source hashes and clean HEAD, and accepted W1's bounded
result. Evidence documentation review and source integration remain separate.
W1 is closed; no automatic rerun, main integration, GitHub sync or product READY
is authorized by this result.
