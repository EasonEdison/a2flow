# Isolated evidence

`python scripts/verify_chat_write_approval.py` passed 80 checks using runtime dependencies, the existing transaction-capable in-memory card fixture, synthetic owner IDs, fake RPC and no network. It covers READ direct execution; zero WRITE calls before confirmation; invalid/foreign-owner submissions; ordinary temporary-route bypass rejection; tampered arguments; immutable approval metadata; concurrent submission and completed replay with one invocation; UNKNOWN no retry; actual ACTION receipt and WRITE_APPROVAL continuation; original handling turn/task/tool; and exact claim/owner/task/arguments gating with other waiting cards blocked.

The handling-task SQL predicate is exercised with a deterministic connection adapter; this probe does not establish PostgreSQL execution or deployed behavior. Parent integration and public acceptance remain required. No live accounts or business operations were used.
