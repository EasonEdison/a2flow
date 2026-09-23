package dev.a2flow.management.support;

/** Explicit environment selection; missing or invalid configuration never implies production. */
public final class DeploymentEnvironment {
    private DeploymentEnvironment() { }
    public static String name() {
        String value = System.getProperty("a2flow.environment", System.getenv("A2FLOW_ENVIRONMENT"));
        if (value == null || !(value.equals("PRT") || value.equals("ONLINE"))) {
            throw new IllegalStateException("A2FLOW_ENVIRONMENT must explicitly be PRT or ONLINE");
        }
        return value;
    }
    public static boolean isProd() { return name().equals("ONLINE"); }
}
