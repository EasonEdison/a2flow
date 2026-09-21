# Management account login

Set `A2FLOW_MANAGEMENT_AUTH_MODE=account` to serve the Chinese account/password
login page at `/login`. The existing `/private-preview/login` and
`/private-preview/logout` paths remain aliases for browser compatibility.
Account mode rejects bearer authentication and token login forms.

Accounts and sessions use the existing B-side `users` and `sessions` repositories
in the configured management PostgreSQL database. No schema is created by this
factory. Provision accounts separately using the existing password hashing and
users repository; roles must be `ADMIN` or `USER`. Current database roles are
resolved for every request. Legacy host user ID and role configuration remains
required for factory compatibility but never supplies account-mode identity.

`A2FLOW_MANAGEMENT_PASSWORD_PEPPER_FILE` must reference the same protected pepper
file used by the B-side account service. The image must include `a2flow_bside`.
`A2FLOW_MANAGEMENT_BROWSER_ORIGIN` remains the primary browser origin.
Optional `A2FLOW_MANAGEMENT_BROWSER_ORIGINS` is a comma-separated exact-origin
allowlist; all entries must use the same scheme. HTTPS uses a Secure cookie.
Sessions last two hours, persist across process restarts, and logout revokes only
the current session. Credentials and session tokens must not be logged.
Login ingress is limited to 4096 bytes and 100 attempts/process/minute,
20/source/minute and 8/account/minute. Proxy forwarding headers are not trusted;
multiple clients behind one proxy can share the source limit.
