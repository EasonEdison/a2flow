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
