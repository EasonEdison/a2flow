package dev.a2flow.management.a2ui.gateway;

import java.util.Map;

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledActionBinding;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledCapabilityActionRef;

import lombok.Value;

/**
 * Action Gateway Slice G 的 transport-neutral 领域 DTO。
 *
 * <p>上游把平台 correlation/idempotency 与官方 v0.9.1 message 分层传入；
 * resolver 输出闭合 Action，mapper 输出精确 CapabilityAction 参数。这里不表达 HTTP/SSE、审批、
 * 执行结果、ResultAdapter、ledger 或 render ack。
 */
public final class A2uiActionGatewayModels {

    private A2uiActionGatewayModels() {
    }

    @Value
    public static class A2uiRuntimeSession {
        private String runtimeSessionToken;
        private String appBuildId;
        private String protocolVersion;
        private String catalogId;
        private String catalogRevision;
        private String catalogDigest;
    }

    @Value
    public static class A2uiActionInvocation {
        private String correlationId;
        private String idempotencyKey;
        private Map<String, Object> message;
    }

    @Value
    public static class A2uiResolvedAction {
        private A2uiActionInvocation invocation;
        private String actionName;
        private String surfaceId;
        private String sourceComponentId;
        private String timestamp;
        private Map<String, Object> actionContext;
        private A2uiCompiledActionBinding binding;
    }

    @Value
    public static class A2uiMappedCapabilityRequest {
        private A2uiCompiledCapabilityActionRef capability;
        private Map<String, Object> arguments;
    }
}
