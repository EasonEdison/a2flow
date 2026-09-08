# A2Flow internal Action Runtime — AF-RUNTIME-02

This is an importable internal Python library, not a published Action wire
contract, HTTP service or production persistence adapter. It consumes the
approved Skill/Policy subset and public LangGraph APIs.

The trusted backend supplies InteractionRepository, ConfigurationPort,
ExecutorPort and a LangGraphContinuation bound to its compiled graph.
The render resolver additionally supplies the full recorded asset-version
closure in recordedVersions. All effective versions must come from the current
PRT/ONLINE backend resolver. An Action request cannot select the backend owner,
environment, graph thread, operation reference, policy or completion result.

ActionService.submit accepts exactly runId, nodeId, interactionId, actionName,
controlRequestId and inputs. It validates ownership and active wait state,
compares the full recorded/current version closure, resolves an allowed Action,
validates configured inputs, then saves an EXECUTING control reservation before
calling the injected executor. Configured result validation and the reviewed
SCHEMA_VALID or JSON_POINTER_EQUALS policy determine business success. Pointer
evaluation reuses installed jsonpointer 3.1.1; booleans are not numbers and a
missing path is not JSON null. Unsupported policies are rejected during config
construction, before executor dispatch.

A failed result or successful non-completing Action stays waiting. Successful
completion records its actual result and resumes only the matching native
interrupt ID. The resume payload contains a saved controlRequestId reference;
the replayed Tool rechecks saved facts, owner, active state and versions. It
marks resume_consumed only after this verification. The graph keeps the original
render context/controlRequestId: an Action request does not regenerate the card.
Direct forged resume success values produce another native wait; stopped or
stale-version errors remain observable.

The Deep Agent assembly requires a terminal guard when using Action-enabled
render Tools. Both sync and async Finalizer paths call the guard, so another
successful Tool with the same name cannot hide a required pending interaction.
The original use_skill evidence survives native checkpoint continuation, while
a new invocation still clears it.

Repository scope serializes admission per trusted user/environment/run without
requiring reentrancy. save commits each record independently
of later exceptions. continuation_scope is a separate run-scoped delivery lock;
native graph execution happens outside the admission lock because Tool replay
may run on an SDK worker thread. A real adapter must coordinate stop acceptance
with the admission boundary. No production implementation of these ports is
shipped; tests use explicit locks and in-memory repository/checkpointer fixtures.

Saved Attempt records distinguish business_success, interaction_completed
(the configured completion decision), and resume_status. NOT_REQUESTED means
no continuation was attempted, DISPATCHING means a dispatch was reserved,
RETURNED means the graph invocation returned (other branches may still wait),
and UNCONFIRMED preserves an exception/unknown delivery. Duplicate identical
control requests return the saved record, including UNCONFIRMED, without
business or graph replay. Reusing an ID with changed payload is rejected.
An executor exception remains EXECUTION_UNCONFIRMED because a side effect may
already have occurred. Fresh request IDs are independent user controls; this
does not claim business exactly-once, compensation or cross-run deduplication.

## Run focused tests

From the server worker repository with its existing Python 3.11 environment:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=packages/contracts/src:services/agent-workflow-runtime/src:services/skill-registry/src:experiments/runtime-phase1:experiments/runtime-phase1/tests \
/home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python \
  -m unittest discover -s services/agent-workflow-runtime/tests -v
```

24 deterministic tests cover admission, all asset-version mismatches, typed
policy evaluation, control deduplication, late stop/version changes, uncertain
execution/delivery, actual Deep Agent interruption/resume/Finalizer, two pending
same-name Tools and native A-waits/B1-to-B2 progression. The integration tests
reuse the existing project-authored Skill material test fixture.

Current limits: no PostgreSQL Action repository, durable control ledger,
multi-process locking proof, async continuation/executor adapter, automatic
delivery recovery, node retry orchestration, full stop/restart service, HTTP
ingress, live model or real business API. Async Finalizer rejection is tested;
that is not evidence for async Action execution. All tests are offline and
memory-backed; Runtime remains NO READY.

References: [LangGraph interrupt replay and resume mapping](https://docs.langchain.com/oss/python/langgraph/interrupts),
[jsonpointer resolver](https://python-json-pointer.readthedocs.io/en/latest/tutorial.html).
