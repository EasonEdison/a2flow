# Isolated PostgreSQL regression

Verified 2026-10-20 on Python 3.11.14, PostgreSQL 16.6, psycopg 3.3.6, LangGraph 1.2.11 / checkpoint-postgres 3.1.2. Fifteen focused checks passed; the final probe was rerun after adding child-process schema validation and the waiting-notice wording. No full unit suite was run, per the user's instruction.

## Results

| Fault or behavior | Observed result |
| --- | --- |
| Lifecycle success + stable event identity | State and outbox commit together; the same event remains one row |
| Different waiting events | Not merged merely because they share a run |
| Deferred commit rejection for succeed / stop / fail | All three transitions roll back lifecycle state and notification outbox; stop control also rolls back |
| Fresh consumer process + duplicate reference | One durable in-app notification |
| Ack error after local commit | Redelivery remains one notification |
| Stale notification claim before / after local persistence | In-app notification restored idempotently; completed when no external sender exists |
| Stale claim with configured external sender | UNKNOWN retained with explicit local-restored marker; no external resend |
| Invalid recovery candidate preceding a valid one | Valid waiting candidate still receives its notification |
| Native nested interrupt committed without notification | Read-only recovery enqueues one waiting notification |
| Normal publication after recovery / repeated recovery | Same interrupt identity, one outbox row |
| Consumed interaction or stopped run | No new waiting notice |
| Recovery worker startup/shutdown | Exits cleanly; never invokes the graph |

The reference transport intentionally injects duplicate delivery and acknowledgement failure. PostgreSQL transactions, fresh-process notification consumption, native nested LangGraph interrupts and checkpoint persistence are real. The synthetic graph is invoked once to create its initial checkpoint. Recovery has an invoke method that raises if called; invocation count remains one. There are zero model calls, business calls or external sends. This does not claim a Redis outage test or deployed/public acceptance.

## Reproduce

From a candidate repository root, build the dependency image (source is mounted read-only so the same image can verify another candidate):

```sh
docker build -f openspec/changes/portfolio-runtime-outbox/Dockerfile.probe -t a2flow-outbox-probe:local .
docker network create a2flow-outbox-probe-net
docker run -d --name a2flow-outbox-probe-pg --network a2flow-outbox-probe-net --memory 256m -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16.6-bookworm
docker exec a2flow-outbox-probe-pg pg_isready -U postgres
# Wait for pg_isready to succeed, then run against this isolated container only:
docker run --rm --name a2flow-outbox-probe --network a2flow-outbox-probe-net --memory 1g -e A2FLOW_PROBE_DATABASE_URL='host=a2flow-outbox-probe-pg dbname=postgres user=postgres' -v "$PWD:/probe:ro" a2flow-outbox-probe:local
# After verification, remove only this probe's container and network:
docker rm -f a2flow-outbox-probe-pg
docker network rm a2flow-outbox-probe-net
```

The private test network exposes no host port. `trust` is for this disposable test container only. Do not use the example for application deployment. The script requires an explicit DSN and creates a random `portfolio_outbox_probe_<uuid>` schema with no public search-path fallback; its finally block drops only that schema. The child process rejects DSNs without that exact isolated search-path form. If killed before cleanup, inspect and remove only the generated probe schema.

The dependency image resolves an existing Runtime-lock psycopg 3.3.5 / scheduler 3.3.6 mismatch by using 3.3.6 only inside the probe build; it does not rewrite product lockfiles. The installed version matches the scheduler requirement. Public SDK downloads are required. The Dockerfile is the exact recipe used for this evidence, not a minimal deployment image.

For a Python environment that already has those repository dependencies installed:

```sh
export PYTHONPATH="$PWD:$PWD/packages/contracts/src:$PWD/packages/asset-store/src:$PWD/services/agent-workflow-runtime/src:$PWD/services/scheduler-mq/src:$PWD/services/skill-registry/src:$PWD/services/capability-registry/src:$PWD/services/a2ui-composer/src"
# Explicitly set A2FLOW_PROBE_DATABASE_URL to an isolated PostgreSQL database.
python openspec/changes/portfolio-runtime-outbox/probe.py
```

## Temporary interaction compatibility and limits

Source verification: `WorkflowActions.render_interaction` passes the generated card's applicationKey into `_render_card`; `temporary_interaction.prepare_interaction` populates applicationKey and applicationVersion. `_render_card` saves these into Interaction and constructs the same native interrupt payload as published A2UI: runId, nodeId, interactionId, applicationKey, versionId. The waiting extractor therefore accepts generated temporary interactions. The probe uses a synthetic payload with this contract; it does not call the generation model or claim full frontend acceptance.

A waiting notification records an observed waiting state. A user can complete or stop the run before delivery; opening the notification must revalidate current state. The notice wording states this explicitly. Native checkpoint and notification enqueue are separate transactions: the periodic projection recovery restores missing notices and never resumes business execution. A legacy random waiting event cannot be unambiguously matched to a native interrupt; an already-waiting run crossing the upgrade can get one additional stable notice. Do not deduplicate all waiting events for a run because later waits are distinct.
