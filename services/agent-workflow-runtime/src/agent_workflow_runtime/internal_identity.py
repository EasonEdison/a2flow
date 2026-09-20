"""Identity at a private, network-trusted Runtime ingress.

These headers identify the end user; they are not credentials. This resolver
must only be installed on the private listener, never behind a public proxy.
"""

from ipaddress import ip_address

from skillweave_contracts import TrustedContext

from .models import ActionRejected


def private_identity(environment):
    if environment not in {"PRT", "ONLINE"}:
        raise ValueError("INVALID_HOST_ENVIRONMENT")

    def resolve(scope):
        peer = scope.get("client")
        try:
            local = bool(peer) and ip_address(peer[0]).is_loopback
        except ValueError:
            local = False
        if not local:
            raise ActionRejected("TRUSTED_CONTEXT_REQUIRED")
        headers = scope.get("headers", ())
        users = [v for k, v in headers if k.lower() == b"x-a2flow-user-id"]
        environments = [v for k, v in headers
                        if k.lower() == b"x-a2flow-environment"]
        if len(users) != 1 or environments != [environment.encode("ascii")]:
            raise ActionRejected("TRUSTED_CONTEXT_REQUIRED")
        # Reject rather than carry browser credentials into execution.
        if any(k.lower() == b"cookie" for k, _ in headers):
            raise ActionRejected("TRUSTED_CONTEXT_REQUIRED")
        try:
            return TrustedContext.from_mapping({
                "userId": users[0].decode("ascii"), "environment": environment,
            })
        except (ValueError, TypeError, UnicodeError):
            raise ActionRejected("TRUSTED_CONTEXT_REQUIRED") from None

    return resolve
