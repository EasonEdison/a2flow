# Close allocated runs when graph construction fails

A run and its start control receipt are committed before the runner constructs its graph. Graph setup can fail while loading published assets, binding Skill tools or constructing the configured model. The old failure helper updated the run only when it received a completed RunGraphBinding. Setup errors therefore emitted a failed event while leaving the run RUNNING, and duplicate start requests returned that stranded state without repeating setup.

Run failure transition now occurs independently of graph construction. The existing lifecycle row-lock guard remains authoritative: STOPPED, SUCCEEDED and prior FAILED are preserved. Graph-specific failure observers still run only for a real binding. A pre-existing terminal state produces no new failed event. Original exceptions and UNCONFIRMED control delivery receipts remain unchanged; there is no automatic retry or compensation.

## Explicit limits

This closes a normal caught setup exception window, not process-kill recovery. Runtime state and SchedulerEventSink currently commit on separate PostgreSQL transactions. Closing that dual-write window requires a transactional outbox design and is not included in this change. Runtime itself still uses sequential bounded graphs, not arbitrary DAG composition.
