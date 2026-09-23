package dev.a2flow.management.capabilityrpc;

import java.util.List;
import io.grpc.BindableService;
import io.grpc.Server;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionExecutor;
import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionToolProvider;

/** Explicit host assembly; shared listener serves Ability and A2UI, not the management HTTP protocol. */
@Configuration
public class RuntimeRpcConfiguration {
    @Bean(destroyMethod = "close")
    public GrpcTargetRegistry grpcTargetRegistry(Environment environment) {
        return GrpcTargetRegistry.fromEnvironment(environment.getRequiredProperty("A2FLOW_CAPABILITY_GRPC_TARGETS_JSON"));
    }
    @Bean public GrpcCapabilityTransport grpcCapabilityTransport(GrpcTargetRegistry targets) {
        return new GrpcCapabilityTransport(targets);
    }
    @Bean public PublishedCapabilityExecutionService publishedCapabilityExecutionService(
            CapabilityActionToolProvider provider, CapabilityActionExecutor executor,
            dev.a2flow.management.agentcore.runtime.tool.CapabilityCatalogQueryService catalog) {
        return new PublishedCapabilityExecutionService(provider, executor, catalog);
    }
    @Bean public CapabilityGrpcService capabilityGrpcService(PublishedCapabilityExecutionService service) {
        return new CapabilityGrpcService(service);
    }
    @Bean public SmartLifecycle runtimeGrpcListener(Environment environment, List<BindableService> services) {
        String mode = environment.getRequiredProperty("A2FLOW_RUNTIME_RPC_MODE");
        if (!mode.equals("LOOPBACK") && !mode.equals("MTLS")) throw new IllegalArgumentException("RPC mode must be explicit LOOPBACK or MTLS");
        int port = Integer.parseInt(environment.getRequiredProperty("A2FLOW_RUNTIME_RPC_PORT"));
        if (port < 1 || port > 65535) throw new IllegalArgumentException("Invalid RPC port");
        return new SmartLifecycle() {
            private volatile Server server;
            @Override public synchronized void start() {
                if (server != null) return;
                try {
                    // Current host deployment is co-located. Never open a public RPC listener implicitly.
                    server = TrustedGrpcServer.start("127.0.0.1", port, mode.equals("LOOPBACK"),
                            environment.getProperty("A2FLOW_RUNTIME_RPC_CERT_FILE"),
                            environment.getProperty("A2FLOW_RUNTIME_RPC_KEY_FILE"),
                            environment.getProperty("A2FLOW_RUNTIME_RPC_ENGINE_CA_FILE"), services);
                } catch (Exception failure) { throw new IllegalStateException("Runtime gRPC listener failed to start", failure); }
            }
            @Override public synchronized void stop() {
                if (server != null) { server.shutdownNow(); server = null; }
            }
            @Override public boolean isRunning() { return server != null && !server.isShutdown(); }
            @Override public int getPhase() { return Integer.MAX_VALUE; }
        };
    }
}
