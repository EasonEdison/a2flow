package dev.a2flow.management.access;

/**
 * Trusted host authentication boundary. The host must provide this bean from its authenticated
 * request context. Request parameters, display names, and client headers are not implementations.
 * There is deliberately no default identity or anonymous fallback.
 */
public interface ManagementIdentityProvider {
    String namespace();
    long userId();
    /** 角色来自已认证账号；未提供角色的集成不能获得管理权限。 */
    default boolean isAdministrator() { return false; }
}
