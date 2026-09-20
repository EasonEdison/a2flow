# Signed64 identity validation

Scope: coordinated internal integer identity and decimal-string browser/header
boundaries. No old-data migration or running-service deployment is included.

Offline checks on the coordinated source:

| Suite | Result |
| --- | --- |
| Shared Python contracts | 20 passed |
| JSON contract fixture matrix | 57 passed |
| Management API | 55 collected, 48 passed, 7 opt-in PG cases skipped |
| Asset store | 23 passed |
| Skill registry | 22 passed |
| B-side API | 47 collected, 46 passed, 1 opt-in preflight skipped |
| Scheduler | 37 passed |
| Management deployment assembly | 12 passed |
| Runtime phase-one experiments | 56 collected, 55 passed, 1 opt-in case skipped |
| Runtime (synthetic model traffic) | 234 collected, 211 passed, 23 opt-in cases skipped |

Disposable PostgreSQL checks: four conversation/schema tests and three personal
memory tests passed. A conversation uses `9223372036854775807`, survives a new
worker instance, rejects duplicate turns and remains isolated by user/environment.
All 15 identity columns created by the fresh B/Runtime/management DDL are BIGINT.
The disposable database contains synthetic data only and is removed after testing.

Boundary tests cover signed64 extremes, zero, values above `2**53`, decimal-string
responses, integer gray matching and malformed IDs. These checks do not claim
that pre-existing databases are compatible or that the deployed page is updated.
