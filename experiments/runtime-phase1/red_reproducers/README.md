# Expected RED reproducers

These scripts record Phase 1 behaviors that the selected SDK does not currently
satisfy. They are excluded from the default green suite and must be run
explicitly. A RED result is evidence for a design decision, not a readiness
claim.

## Parallel wait progression

~~~bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=packages/contracts/src:experiments/runtime-phase1 \
/home/admin/OpenSource/.venvs/skillweave-runtime-p1/bin/python -m unittest \
experiments/runtime-phase1/red_reproducers/test_parallel_progression_probe.py -v
~~~

With LangGraph 1.2.11, `wait_a` interrupts while `run_b1` completes in the same
superstep. The invoke returns before `run_b2` can execute, so the assertion
expects `["B1", "B2"]` but observes `["B1"]`. No fallback scheduler is provided
by this experiment.
