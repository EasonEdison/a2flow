# Readiness

SOURCE READY for integration after review. Shared-PostgreSQL admission and
isolated M/B HTTP contracts passed. No full unit suite was executed.

PUBLIC NOT READY: apply the explicit guard SQL before restarting account hosts;
configure shared budgets, registration policy and exact trusted proxies; ensure
every proxy overwrites/preserves only the verified client-IP header; then verify
public TLS, normal account flows, throttling and fail-closed responses. This
workstream does not perform deployment or alter existing users.
