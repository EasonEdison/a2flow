package dev.a2flow.management.managementagent;

import dev.a2flow.management.access.ManagementIdentityProvider;

/** Existing HTTP requests still resolve their Cookie once; granted RPC calls never parse it again. */
public final class TrustedManagementIdentityProvider implements ManagementIdentityProvider {
    private final ManagementIdentityProvider browser;
    public TrustedManagementIdentityProvider(ManagementIdentityProvider browser) { this.browser = browser; }
    @Override public String namespace() { var grant = ManagementOperationContext.current(); return grant == null ? browser.namespace() : grant.namespace(); }
    @Override public long userId() { var grant = ManagementOperationContext.current(); return grant == null ? browser.userId() : grant.userId(); }
    @Override public boolean isAdministrator() { return ManagementOperationContext.current() == null ? browser.isAdministrator() : true; }
}
