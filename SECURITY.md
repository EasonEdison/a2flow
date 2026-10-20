# Security policy

A2Flow is an experimental application platform, not a hardened multi-tenant hosting service. Maintainers prioritize the current `main` branch; no long-term supported release or response-time SLA is declared.

## Reporting

Do not put secrets, exploit payloads, personal records or a working vulnerability in a public issue. Use GitHub's private **Report a vulnerability** action on the repository Security tab if it is available. If it is unavailable, open a public issue containing only a request for a private reporting channel; wait for a channel before sharing sensitive details. No private reporting address or GitHub setting is implied by this document.

Include the affected commit, component, minimal synthetic reproduction, expected/actual boundary and impact. Never test against another user's account or the public demonstration without explicit authorization.

## Deployment boundary

- Serve password authentication over HTTPS with an exact trusted-origin configuration. The historical demonstration's plain-HTTP endpoint is not a secure public-account template.
- Keep database, Runtime and business RPC listeners private; use the configured mTLS boundaries. Do not publish Compose host-network ports blindly.
- Provision credentials outside Git; there are no supported default admin passwords. Password hashes are not recoverable passwords.
- Treat administrator-installed JavaScript component bundles as executable trusted code. The preview loader is not a sandbox for untrusted uploads.
- Keep environment/user ownership checks at service boundaries. A validated entry request does not authorize arbitrary downstream resources.

## Known limitations

M/B share PostgreSQL-backed login and registration admission before password hashing. Budgets survive process restart; trusted proxies must be configured explicitly and overwrite the dedicated client address header. Authentication storage failures return a safe 503, not an in-memory bypass. New self-hosted installs disable public registration by default. See [account policy](deploy/accounts/README.md) and [operator account recovery](docs/account-recovery.md). These application controls are not a volumetric denial-of-service defense.

No independent penetration test, compliance certification, disaster-recovery drill or high-availability certification is claimed. See [quality roadmap](docs/quality-roadmap.md) for the explicit remaining engineering work.
