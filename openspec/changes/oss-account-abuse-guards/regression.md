# Regression

Implemented-source validation (2026-10-20), separate from public deployment:

- An isolated disposable PostgreSQL database admitted exactly 7 of 32 attempts
  from 8 independent worker processes, denying 25 against a shared budget of 7.
  Every worker used an independent connection and guard instance.
- Username budget persisted across separate instances and source IP changes;
  changing case did not bypass it. Database timestamp expiry allowed a later
  attempt after expired records were removed.
- Five proxy cases covered untrusted-header spoofing and trusted missing,
  malformed, comma-separated and duplicate headers.
- Isolated M/B HTTP clients shared one login budget. Rejected credentials on
  either surface counted; both returned 429 and Retry-After when exhausted.
  An explicit hash sentinel confirmed denied attempts did not run scrypt.
- Synthetic PostgreSQL user registration, B login/session/logout and M
  login/logout succeeded. Wrong Origin was rejected before counting.
- Explicit registration disablement and registration admission quota passed.
- A simulated unavailable guard backend returned 503 and a generated correlation
  identifier, matching a safe log. A sensitive exception-message sentinel was
  absent from the log.
- Disposable database was dropped after verification. No existing users, sessions,
  business data, workflows or plans were changed.
- A subsequent Mac-local candidate-source probe covered B account storage,
  B session middleware (including cookie-bearing requests), and M account
  middleware database failures. All returned 503 with server correlation;
  sensitive exception text was absent. No service container was used for this
  follow-up probe. Seven modified Python files passed local AST parsing.
- Existing offline account test fixtures now explicitly inject fake guards; these
  fakes exist only in test files and are not a production fallback. No full unit
  suite was executed.

Public deployment, TLS/proxy checks and runtime acceptance are root-owned and
are not established by these isolated checks.

## Public reproducer and recovery exercise

The checked-in `scripts/verify_account_guard.py` was run on Mac Python 3.11 against
a separate disposable PostgreSQL 16.6 container in the local Colima context. The
final run used FastAPI 0.141.1, Starlette 1.6.0, Pydantic 2.13.5, psycopg 3.3.6,
SQLAlchemy 2.0.54 and httpx 0.28.1. It passed shared M/B admission, 32 competing
process requests with 7 admitted/25 denied, proxy validation, registration/login
and safe backend-failure correlation.

A synthetic administrator's hash update and deletion of that user's sessions were
committed in one transaction. Old M/B sessions became invalid, the old password
failed, and the new password logged in through both hosts. The operator guide
uses the same transaction but never promotes or creates a real user. This proof
is synthetic; no production account recovery or backup restoration is claimed.

Six unsafe invocations were rejected: wrong database name, remote host, permissive
DSN permissions, symlink DSN, PGHOSTADDR override, and a nonempty database. The
existing synthetic sentinel row remained unchanged. No probe schema remained.
The dedicated PostgreSQL container and generated test credential files were
removed afterwards. No ECS service container was used for this follow-up.
