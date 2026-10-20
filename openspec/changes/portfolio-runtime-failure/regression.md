# Focused verification

Executed against the worker source using the existing runtime Python environment and existing RunRepository/RecordingSink adapters. The probe invoked the real ControlledRunRunner.start and RunLifecycle; graph construction and graph invoke raised one synthetic ValueError. No model, database, scheduler, network business call or production mutation occurred. This is a deterministic boundary probe, not PostgreSQL or public-runtime proof. A full unit suite was intentionally not run.

| Scenario | Before | After |
| --- | --- | --- |
| Graph factory raises after allocation | RUNNING; 1 failed event | FAILED; 1 failed event |
| Bound graph invoke raises | FAILED; 1 failed event | FAILED; 1 failed event |
| Stop wins before setup exception | STOPPED; 1 failed event | STOPPED; 0 failed events |
| Completed state exists before late setup exception | SUCCEEDED; 1 failed event | SUCCEEDED; 0 failed events |

Every scenario retained the original exception object, UNCONFIRMED start delivery, zero operation facts and exactly one graph factory call after repeating the same control request. Duplicate start requests returned the saved run status without re-executing. The terminal-state cases were synthetic race-boundary probes, not claims of ordinary setup completing a graph.

`git diff --check` passed. Source is ready for coordinator integration. Deployment and public acceptance have not been performed for this change.
