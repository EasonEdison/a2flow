package dev.a2flow.management.capabilityrpc;

import java.io.File;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import io.grpc.ManagedChannel;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;
import io.grpc.netty.shaded.io.grpc.netty.GrpcSslContexts;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.support.JsonSupport;

/** Host configuration only. Each environment has its own endpoint; there is no fallback. */
public final class GrpcTargetRegistry implements AutoCloseable {
    public record Endpoint(String host, int port, boolean loopbackPlaintext,
            String trustCertFile, String clientCertFile, String clientKeyFile) { }
    private final Map<String, Map<ReleaseEnvironment, Endpoint>> targets;
    private final Map<String, ManagedChannel> channels = new ConcurrentHashMap<>();
    public GrpcTargetRegistry(Map<String, Map<ReleaseEnvironment, Endpoint>> targets) {
        Map<String, Map<ReleaseEnvironment, Endpoint>> copy = new java.util.LinkedHashMap<>();
        targets.forEach((key, values) -> copy.put(key, Map.copyOf(values)));
        this.targets = Map.copyOf(copy);
    }
    public static GrpcTargetRegistry fromEnvironment(String json) {
        if (json == null || json.isBlank()) throw new IllegalArgumentException("A2FLOW_CAPABILITY_GRPC_TARGETS_JSON required");
        var type = JsonSupport.mapper().getTypeFactory().constructMapType(Map.class, JsonSupport.mapper().constructType(String.class),
                JsonSupport.mapper().getTypeFactory().constructMapType(Map.class, ReleaseEnvironment.class, Endpoint.class));
        try { return new GrpcTargetRegistry(JsonSupport.mapper().readValue(json, type)); }
        catch (java.io.IOException e) { throw new IllegalArgumentException("Invalid gRPC target configuration", e); }
    }
    public ManagedChannel channel(String key, ReleaseEnvironment environment) {
        Endpoint endpoint = targets.getOrDefault(key, Map.of()).get(environment);
        if (endpoint == null) throw new IllegalArgumentException("No gRPC target for exact key/environment");
        return channels.computeIfAbsent(key + ":" + environment, ignored -> open(endpoint));
    }
    private ManagedChannel open(Endpoint value) {
        if (value.host() == null || !value.host().matches("[A-Za-z0-9.-]+") || value.port() < 1 || value.port() > 65535) {
            throw new IllegalArgumentException("Explicit gRPC host/port required");
        }
        var builder = NettyChannelBuilder.forAddress(value.host(), value.port()).disableRetry()
                .maxInboundMessageSize(5 * 1024 * 1024);
        if (value.loopbackPlaintext()) {
            if (!"127.0.0.1".equals(value.host())) throw new IllegalArgumentException("Plaintext only on explicit IPv4 loopback");
            return builder.usePlaintext().build();
        }
        if (value.trustCertFile() == null || value.clientCertFile() == null || value.clientKeyFile() == null) {
            throw new IllegalArgumentException("Production downstream gRPC requires mTLS credentials");
        }
        try {
            return builder.sslContext(GrpcSslContexts.forClient().trustManager(new File(value.trustCertFile()))
                    .keyManager(new File(value.clientCertFile()), new File(value.clientKeyFile())).build()).build();
        } catch (javax.net.ssl.SSLException e) { throw new IllegalArgumentException("Invalid mTLS configuration", e); }
    }
    @Override public void close() { channels.values().forEach(ManagedChannel::shutdownNow); }
}
