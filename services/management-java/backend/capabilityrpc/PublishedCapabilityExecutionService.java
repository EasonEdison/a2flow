package dev.a2flow.management.capabilityrpc;

import java.util.Map;
import java.util.Objects;
import org.springframework.ai.chat.model.ToolContext;
import dev.a2flow.management.agentcore.runtime.engine.model.BaseAgentContext;
import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionExecutor;
import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionToolProvider;
import dev.a2flow.management.agentcore.runtime.tool.TrustedToolContext;
import dev.a2flow.management.model.CapabilityActionExecutionPlan;
import dev.a2flow.management.model.CapabilityToolResult;

/** Shared published DB resolution. Caller admission belongs to trusted engine / frozen A2UI binding. */
public final class PublishedCapabilityExecutionService implements CapabilityExecutionPort {
    public record CurrentExecution(CapabilityActionExecutionPlan plan, CapabilityToolResult result) { }
    private final CapabilityActionToolProvider provider;
    private final CapabilityActionExecutor executor;
    private final dev.a2flow.management.agentcore.runtime.tool.CapabilityCatalogQueryService catalog;
    public PublishedCapabilityExecutionService(CapabilityActionToolProvider provider, CapabilityActionExecutor executor,
            dev.a2flow.management.agentcore.runtime.tool.CapabilityCatalogQueryService catalog) {
        this.provider = provider; this.executor = executor; this.catalog = catalog;
    }
    public CapabilityActionExecutionPlan resolve(String assetKey, CapabilityRpcContext context) {
        var plan = provider.resolveReleasedPlan(assetKey, context.environment(), context.userId(), context.client());
        if (plan.getResolvedEnvironment() != context.environment() || plan.getSourceId() == null
                || plan.getSourceDigest() == null) throw new IllegalArgumentException("Exact published source required");
        return plan;
    }
    @Override public CapabilityToolResult execute(String assetKey, String argumentsJson, CapabilityRpcContext context) {
        return executePlan(resolve(assetKey, context), argumentsJson, context);
    }
    public CurrentExecution executeCurrent(String assetKey, String argumentsJson, CapabilityRpcContext context) {
        var plan = resolve(assetKey, context);
        return new CurrentExecution(plan, executePlan(plan, argumentsJson, context));
    }
    @Override public CapabilityToolResult executeActionCode(String actionCode, String argumentsJson, CapabilityRpcContext context) {
        String assetKey = catalog.requireAssetKey(actionCode, context.environment(), context.userId(), context.client());
        var plan = resolve(assetKey, context);
        if (!Objects.equals(actionCode, plan.getActionCode())) {
            throw io.grpc.Status.FAILED_PRECONDITION.withDescription("CAPABILITY_ACTION_CODE_CHANGED").asRuntimeException();
        }
        return executePlan(plan, argumentsJson, context);
    }
    private CapabilityToolResult executePlan(CapabilityActionExecutionPlan plan, String json, CapabilityRpcContext context) {
        BaseAgentContext agent = new BaseAgentContext();
        agent.setUserId(context.userId()); agent.setClient(context.client()); agent.setEnv(context.environment().name());
        var toolContext = new ToolContext(Map.of("agentContext", agent, TrustedToolContext.TRACE_ID, context.requestId()));
        return executor.executeResult(plan, json, toolContext, context.environment(), context.environment());
    }
}
