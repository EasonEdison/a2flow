# AF-RUNTIME-05 readiness

Status: NO READY — source candidate with in-process evidence, pending main-brain review.
No server-main/GitHub integration or deployment claimed by this candidate.

Implemented: formal controlled service/assembly, Runtime-local FastAPI adapter, trusted host context, canonical start receipt lookup, node-bound Action, stop/fresh restart, bounded shared progress/event projection, separate execution/read/stop capacity, actual byte bounds and error redaction.

Evidence and exact gates: regression-05.md. Design/route/ownership/lifetime limits: service-entry-05.md.
Dependencies: AF05-D1 authorized three verified project-venv wheels only; old unique61 versions unchanged, final unique64, pip check/imports PASS.

Remaining acceptance boundary:
- Coordinator source review and a separate integration release.
- New readonly PostgreSQL projection has no live PG execution evidence in this slice.
- HTTP tests use HTTPX in-process ASGI and direct cancellation/disconnect harnesses; no actual listening socket, proxy, server shutdown or distributed-host concurrency claim.
- Synthetic model/business/asset factories and MemorySaver do not establish live provider/business integration or production persistence.
- Snapshot output is not a final card/result UI, token stream, transition history, delivery guarantee or durable replay.
- Lifecycle RUNNING/STOPPED and stored operation facts are not process liveness or physical cancellation guarantees.
- Backend still supplies trusted identity, authorized definition/entry/current configuration, controlled graph and checkpointer session lifecycle. No full Workflow definition compiler, scheduler/recovery worker, public auth protocol or deployment is included.

Do not archive this slice as production-ready or infer standing PG/listener/provider permissions.
