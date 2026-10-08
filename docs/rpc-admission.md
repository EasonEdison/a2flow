# RPC admission and parallel tools

The joint A2UI/capability host and the standalone capability host use four
execution threads. They accept at most sixteen unfinished RPCs: four active
handlers and up to twelve waiting requests. This bounds the executor queue
without rejecting an ordinary burst of parallel tools and contract reads.

This is admission waiting, not a retry. Existing deadlines and the handler's
`context.is_active()` check still apply. Overflow remains RESOURCE_EXHAUSTED;
the Agent client preserves it as RPC_RESOURCE_EXHAUSTED. Transport logs contain
only the gRPC status name, never provider detail, payload, identity or credentials.
No completed Action, unknown execution, or failed workflow is replayed.

## Evidence (2026-10-08)

- Before: six simultaneous read-only calls against the deployed execution host
  produced four successful results and two RESOURCE_EXHAUSTED failures; three
  simultaneous reads succeeded.
- Isolated real gRPC probe: six requests succeed, peak executing handlers is four,
  and request seventeen is rejected without entering the handler.
- Compile and focused static checks pass. No dependency or schema change.
- The earlier workflow checkpoint recorded RPC_EXECUTION_FAILED, not the original
  transport status. The capacity issue is reproduced but cannot retrospectively
  be proven to be that run's exact cause.
- Deployment and a fresh complete workflow regression are pending. Do not infer
  end-to-end readiness from the isolated admission check.
