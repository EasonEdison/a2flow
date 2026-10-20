# Shared account admission guards

Status: APPROVED FOR IMPLEMENTATION; deployment and runtime proof pending.

Public M and B login share users but only M has a process-local limiter. B authentication can consume unbounded expensive password verification work. Proxy loopback addresses cannot identify a browser safely without an explicit trust boundary.

Use a single PostgreSQL-backed sliding-window admission guard before password verification, with shared M/B login budgets and a separate registration budget. Preserve password hashing, existing sessions, exact Origin enforcement and normal registration when enabled. No captcha, automatic retries, password changes or account lockout is introduced.

Approved defaults: login 100 total, 20 per IP, 8 per username per 60 seconds; registration 30 total, 5 per IP, 3 per username per 3600 seconds. Operators may explicitly configure limits. Registration remains enabled in the existing deployment.
