# Design

A shared account_auth_attempts table records only HMAC-derived address/username keys and timestamps. Each environment/action admission holds a transaction advisory lock, uses database time, prunes expired entries, checks all limits, and inserts one accepted attempt before password verification. Successful and unsuccessful credentials consume the same budget. Denied requests do not hash passwords. Cross-process races cannot exceed the configured budget. A database failure returns 503 and a safe correlation identifier; no process-local fallback exists.

The transport peer is authoritative by default. Only explicitly configured exact proxy IPs may supply one X-A2Flow-Client-IP header containing one valid IP address. Other forwarded headers are ignored. Proxy configuration must overwrite the header using the actual client address. An empty trusted-proxy list is the default. Launchers retain proxy_headers=False.

Schema installation is an explicit operator step; startup checks readiness without DDL. Existing login/registration and session database work runs in the framework bounded thread pool. Configuration carries explicit registration enablement and configurable limits. Passwords, session values, raw IPs and usernames never enter guard records or logs.
