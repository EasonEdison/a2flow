package dev.a2flow.management.capabilityrpc;

import dev.a2flow.management.model.CapabilityToolResult;

/** In-process trusted A2UI adapter and gRPC service share the exact same execution path. */
public interface CapabilityExecutionPort {
    CapabilityToolResult execute(String assetKey, String argumentsJson, CapabilityRpcContext context);
    CapabilityToolResult executeActionCode(String actionCode, String argumentsJson, CapabilityRpcContext context);
}
