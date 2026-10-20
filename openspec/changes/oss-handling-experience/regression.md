# Regression

## Source and bounded validation

TypeScript/Vite build passed. Actual PostgreSQL rollback probe verified running/failed/completed delivery projection in both detail and activity rail; running and interrupted confirmation rejected, completed confirmation accepted. All probe writes rolled back. Full unit suite not run per owner direction.

The confirmation guard now checks the latest model delivery under the task lock: an early successful business operation cannot make a still-active model turn confirmable. Existing waiting-input and uncertain-operation guards remain required. FAILED/UNKNOWN were inspected in source and bounded probes; no forced uncertain business execution was performed on the public service.

## Public acceptance, 2026-10-20

B API and frontend deployed from b21700f54487c425006b6fa8adf2066897d9ede5. Existing runtime image and real-chat launcher retained; workflow executor unchanged. No schema change in this slice. All 72 frontend source hashes match the integrated checkout; all seven public assets match the built files.

Used the existing scheduled-anomaly handling task and its saved records. Did not rerun the schedule, workflow, model turn or business writes. Verified readable operation names, titles, result identifiers/revisions/times, Markdown preview and collapsed technical details. Public acceptance exposed the nested manuscript title shape; corrected it and deployed the fix before final verification.

One normal UI confirmation at 16:33:40 Asia/Shanghai saved a scoped completion statement: the review-record draft task is complete, while actual personnel review and the original anomaly remain unresolved. The detail immediately showed the confirmation, time and statement. Reload retained the same task and the activity rail showed the same confirmed state. Opening the original conversation did not send a message or invoke tools.

Before/after-refresh database snapshots are identical. Compared with the earlier handling acceptance, only the handling task status, completion statement and timestamps changed. Five returned operations, two model turns, one submitted temporary card, one project, one source, one manuscript and three business-write receipts are unchanged. Original workflow facts, anomaly and acknowledgement remain unchanged; the acceptance schedule remains disabled.
