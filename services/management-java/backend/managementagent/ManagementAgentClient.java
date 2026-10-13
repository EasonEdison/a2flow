package dev.a2flow.management.managementagent;

import java.util.concurrent.TimeUnit;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Status;
import org.springframework.core.env.Environment;
import dev.a2flow.management.managementagent.proto.ManagementAgentGrpc;

/** Internal host-only RPC. No browser Cookie, public target, retry or HTTP fallback. */
public final class ManagementAgentClient implements AutoCloseable {
    private final ManagedChannel channel;
    public ManagementAgentClient(Environment environment) {
        String target = environment.getProperty("A2FLOW_MANAGEMENT_AGENT_TARGET");
        if (target == null || target.isBlank()) { channel = null; return; }
        if (!target.matches("127\\.0\\.0\\.1:[0-9]{1,5}")) throw new IllegalArgumentException("Management Agent target must be explicit loopback host:port");
        int port = Integer.parseInt(target.substring(target.lastIndexOf(':') + 1));
        if (port < 1 || port > 65535) throw new IllegalArgumentException("Management Agent port is invalid");
        channel = ManagedChannelBuilder.forAddress("127.0.0.1", port).usePlaintext().disableRetry()
                .maxInboundMessageSize(16 * 1024 * 1024).build();
    }
    public ManagementAgentGrpc.ManagementAgentBlockingStub stub() {
        if (channel == null) throw Status.UNAVAILABLE.withDescription("MANAGEMENT_AGENT_NOT_CONFIGURED").asRuntimeException();
        return ManagementAgentGrpc.newBlockingStub(channel).withDeadlineAfter(20, TimeUnit.SECONDS);
    }
    @Override public void close() { if (channel != null) channel.shutdownNow(); }
}
