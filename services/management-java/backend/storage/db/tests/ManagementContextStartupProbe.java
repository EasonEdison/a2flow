package dev.a2flow.management.host;

import java.net.InetAddress;
import java.net.ServerSocket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.context.SmartLifecycle;
import org.springframework.core.env.MapPropertySource;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionExecutor;
import dev.a2flow.management.capabilityrpc.CapabilityApprovalGuard;
import dev.a2flow.management.capabilityrpc.CapabilityApprovalStore;
import dev.a2flow.management.capabilityrpc.PostgresCapabilityApprovalStore;
import dev.a2flow.management.config.ManualManagementConfiguration;

/** Real production composition root, disposable PG, no replaced beans or business calls. */
public final class ManagementContextStartupProbe {
    private ManagementContextStartupProbe() { }

    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !args[0].equals("jdbc:postgresql://127.0.0.1:5432/a2flow_management_probe")
                || !args[1].equals("probe")) {
            throw new IllegalArgumentException("Dedicated local runner database required");
        }
        String password = System.getenv("A2FLOW_PROBE_DB_PASSWORD");
        if (password == null || password.isBlank()) throw new IllegalArgumentException("Probe password required");
        Path directory = Files.createTempDirectory("a2flow-management-context-");
        String previousConfig = System.getProperty("a2flow.management.config");
        String previousHosts = System.getProperty("jdk.net.hosts.file");
        HikariDataSource pool = null;
        SmartLifecycle listener = null;
        int checks = 0;
        try {
            // The shared network-none sandbox has no DNS; resolve its own UTS
            // hostname locally for MyBatis ID initialization, without egress.
            String hostname = Files.readString(Path.of("/proc/sys/kernel/hostname")).strip();
            if (!hostname.matches("[A-Za-z0-9.-]+")) throw new IllegalArgumentException("Invalid sandbox hostname");
            Path hosts = directory.resolve("hosts");
            Files.writeString(hosts, "127.0.0.1 localhost " + hostname + "\n");
            System.setProperty("jdk.net.hosts.file", hosts.toString());
            Path config = directory.resolve("management.json");
            Files.writeString(config, "{\"workspaceRoot\":\"" + directory.resolve("workspace")
                    + "\",\"workspaceChangeGuard\":{},\"pages\":{}}");
            System.setProperty("a2flow.management.config", config.toString());
            Map<String, Object> properties = new LinkedHashMap<>();
            properties.put("A2FLOW_MANAGEMENT_JDBC_URL", args[0]);
            properties.put("A2FLOW_MANAGEMENT_DB_USER", args[1]);
            properties.put("A2FLOW_MANAGEMENT_DB_PASSWORD", password);
            properties.put("A2FLOW_MANAGEMENT_DB_POOL_SIZE", "1");
            properties.put("A2FLOW_MANAGEMENT_NAMESPACE", "context-probe");
            properties.put("A2FLOW_CAPABILITY_GRPC_TARGETS_JSON", "{}");
            properties.put("A2FLOW_RUNTIME_RPC_MODE", "LOOPBACK");
            try (ServerSocket socket = new ServerSocket(0, 1, InetAddress.getLoopbackAddress())) {
                properties.put("A2FLOW_RUNTIME_RPC_PORT", Integer.toString(socket.getLocalPort()));
            }
            for (String environment : new String[]{"PRT", "ONLINE"}) {
                String prefix = "A2FLOW_PUBLICATION_" + environment + "_";
                // These lazy adapters are composed but never asked to publish or connect.
                properties.put(prefix + "JDBC_URL", args[0]);
                properties.put(prefix + "USER", args[1]);
                properties.put(prefix + "PASSWORD", password);
                properties.put(prefix + "DATABASE", "a2flow_probe_" + environment.toLowerCase());
                properties.put(prefix + "NAMESPACE", "context-probe");
            }
            try (var application = new AnnotationConfigWebApplicationContext()) {
                application.getEnvironment().getPropertySources().addFirst(
                        new MapPropertySource("isolated-probe", properties));
                application.register(ManualManagementConfiguration.class);
                application.refresh();
                require(application.isActive(), "Production application context did not start"); checks++;
                require(application.getBeansOfType(CapabilityApprovalGuard.class).size() == 1,
                        "Exactly one real approval guard must be registered"); checks++;
                require(application.getBean(CapabilityApprovalStore.class) instanceof PostgresCapabilityApprovalStore,
                        "Production PostgreSQL approval store missing"); checks++;
                require(application.getBean(CapabilityActionExecutor.class) != null,
                        "Executor dependency injection failed"); checks++;
                pool = application.getBean(HikariDataSource.class);
                try (var connection = pool.getConnection(); var statement = connection.createStatement();
                        var rows = statement.executeQuery("SELECT current_database()")) {
                    require(rows.next() && rows.getString(1).equals("a2flow_management_probe"),
                            "Wrong probe database"); checks++;
                }
                listener = application.getBean("runtimeGrpcListener", SmartLifecycle.class);
                require(listener.isRunning(), "Actual Runtime gRPC lifecycle did not start"); checks++;
            }
            require(pool.isClosed(), "Application shutdown leaked database pool"); checks++;
            require(!listener.isRunning(), "Application shutdown leaked gRPC listener"); checks++;
        } finally {
            if (previousConfig == null) System.clearProperty("a2flow.management.config");
            else System.setProperty("a2flow.management.config", previousConfig);
            if (previousHosts == null) System.clearProperty("jdk.net.hosts.file");
            else System.setProperty("jdk.net.hosts.file", previousHosts);
            try (var files = Files.walk(directory)) {
                for (Path file : files.sorted(Comparator.reverseOrder()).toList()) Files.delete(file);
            }
        }
        System.out.println("{\"probe\":\"management-context\",\"result\":\"PASS\",\"checks\":" + checks
                + ",\"postgres\":true,\"productionComposition\":true,\"businessCalls\":0}");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }
}
