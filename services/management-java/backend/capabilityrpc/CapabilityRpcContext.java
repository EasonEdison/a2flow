package dev.a2flow.management.capabilityrpc;

import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.capabilityrpc.proto.ExecutionContext;

/** Only trusted hosts construct this authority; never merge it with model arguments. */
public record CapabilityRpcContext(long userId, ReleaseEnvironment environment, String requestId, String client) {
    public CapabilityRpcContext {
        if (environment == null || requestId == null || requestId.isBlank() || requestId.length() > 200
                || !("PC".equals(client) || "APP".equals(client) || "COMMON".equals(client))) {
            throw new IllegalArgumentException("Explicit userId/environment/requestId/client context required");
        }
    }
    public static CapabilityRpcContext fromProto(ExecutionContext value) {
        if (!value.hasUserId()) throw new IllegalArgumentException("userId presence required");
        ReleaseEnvironment environment = switch (value.getEnvironment()) {
            case PRT -> ReleaseEnvironment.PRT;
            case ONLINE -> ReleaseEnvironment.ONLINE;
            default -> throw new IllegalArgumentException("PRT or ONLINE required");
        };
        return new CapabilityRpcContext(value.getUserId(), environment, value.getRequestId(), value.getClient());
    }
    public ExecutionContext toProto() {
        return ExecutionContext.newBuilder().setUserId(userId)
                .setEnvironment(dev.a2flow.management.capabilityrpc.proto.Environment.valueOf(environment.name()))
                .setRequestId(requestId).setClient(client).build();
    }
}
