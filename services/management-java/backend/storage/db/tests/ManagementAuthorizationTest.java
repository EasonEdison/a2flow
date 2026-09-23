package dev.a2flow.management.access;

import java.lang.reflect.Field;
import java.lang.reflect.Method;

import dev.a2flow.management.release.ReleaseAssetType;

/** 不访问数据库，检查统一账号角色与可信 operator 边界。 */
public final class ManagementAuthorizationTest {
    public static void main(String[] args) throws Exception {
        AssetAuthorizationService service = new AssetAuthorizationService();
        Field field = AssetAuthorizationService.class.getDeclaredField("managementIdentityProvider");
        field.setAccessible(true);
        field.set(service, identity(false));
        String userId = Long.toString(Long.MAX_VALUE);
        service.requireTrustedOperator(userId);
        if (service.isAdmin(userId)) throw new AssertionError("USER granted ADMIN");
        try {
            service.requireTrustedOperator("1");
            throw new AssertionError("Forged operator accepted");
        } catch (SecurityException expected) { }
        boolean rejected = false;
        try {
            service.validateCreationOwners(userId, ReleaseAssetType.SKILL, "sample", null);
        } catch (RuntimeException expected) {
            rejected = true;
        }
        if (!rejected) throw new AssertionError("USER permitted asset creation");
        field.set(service, identity(true));
        if (!service.isAdmin(userId) || service.isAdmin("1")) throw new AssertionError("ADMIN identity mismatch");
        if (!service.validateCreationOwners(userId, ReleaseAssetType.SKILL, "sample", null).equals(java.util.List.of(userId))) {
            throw new AssertionError("Creator identity lost");
        }
        // OWNER 只是资产归属，不提升普通账号的编辑权限。
        Class<?> role = Class.forName("dev.a2flow.management.access.AssetAccessRole");
        Method permissions = AssetAuthorizationService.class.getDeclaredMethod("permissions", role);
        permissions.setAccessible(true);
        Object owner = java.util.Arrays.stream(role.getEnumConstants()).filter(v -> v.toString().equals("OWNER")).findFirst().orElseThrow();
        Object value = permissions.invoke(service, owner);
        if ((Boolean) value.getClass().getMethod("isCanEdit").invoke(value)) throw new AssertionError("OWNER bypassed account role");
        System.out.println("PASS: trusted signed64 operator and shared account role authorization");
    }

    private static ManagementIdentityProvider identity(boolean administrator) {
        return new ManagementIdentityProvider() {
            public String namespace() { return "test"; }
            public long userId() { return Long.MAX_VALUE; }
            public boolean isAdministrator() { return administrator; }
        };
    }
}
