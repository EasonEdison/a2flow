package dev.a2flow.management.a2ui.runtime;

import java.util.List;
import java.util.Map;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationBuild;
import dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiActionInvocation;
import dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiRuntimeSession;
import dev.a2flow.management.release.ReleaseEnvironment;

/** 仅服务间可信 RPC 使用；浏览器不得提交卡片快照、身份或发布 Build。 */
public final class A2uiRuntimeContracts {
    private A2uiRuntimeContracts() { }
    public record ReleaseIdentity(String appCode, String sourceId, String digest,
            String appBuildId, ReleaseEnvironment environment) { }
    public record PublishedApplication(ReleaseIdentity identity, A2uiApplicationBuild build) { }
    public record ActivateRequest(String appCode, Map<String, Object> params) { }
    /** Python 从持久化读取并鉴权；Action 始终按当前用户与环境的有效发布解析。 */
    public record TrustedCard(long userId, String appCode,
            Map<String, Object> params, List<Map<String, Object>> snapshot) { }
    public record ActionRequest(TrustedCard card, A2uiActionInvocation invocation) { }
    public record ExecutionSummary(String bindingId, String actionCode, boolean success,
            int capabilityVersion, String errorCode) { }
    public record ActionDescriptor(String surfaceId, String componentId, String actionName,
            Map<String, Object> contextSchema) { }
    public record CatalogDescriptor(String protocolVersion, String catalogId,
            String catalogRevision, String catalogDigest) { }
    public record Description(ReleaseIdentity release, Map<String, Object> paramsSchema,
            String interactionMode, List<ActionDescriptor> actions, CatalogDescriptor catalog) { }
    public record RuntimeResult(ReleaseIdentity release, Map<String, Object> params,
            List<Map<String, Object>> messages, List<Map<String, Object>> snapshot,
            List<ExecutionSummary> executions, List<ActionDescriptor> actions, boolean completeInteraction,
            String selectedBranchId, CatalogDescriptor catalog, A2uiRuntimeSession session,
            String interactionMode, boolean businessSuccess) { }
    public static final class RuntimeFailure extends IllegalStateException {
        private final String code;
        public RuntimeFailure(String code) { super(code); this.code = code; }
        public String getCode() { return code; }
    }
}
