package dev.a2flow.management.agentcore.runtime.tool;

import java.util.LinkedHashMap;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineContext;

/**
 * Agent-core 可信工具上下文构建器。
 *
 * <p>上游 Agent 宿主把不允许模型控制的运行事实写入 {@link AgentEngineContext}，本类在调用 Tool 前
 * 将这些事实合并到 Spring ToolContext。普通业务上下文即使携带同名字段也会被移除，防止模型参数或
 * 外部 Chat 请求伪造发布环境。本类只负责上下文隔离和透传，不选择环境、不做缺省回退，也不解释
 * capability 或未来 {@code ORCHESTRATION_CONFIG} dependency adapter 的领域内容。本期没有注册或
 * 执行 orchestration adapter；这里只保留二者可以复用的可信上下文扩展点。
 */
public final class TrustedToolContext {

    public static final String RELEASE_ENVIRONMENT = "releaseEnvironment";
    public static final String TRACE_ID = "traceId";
    public static final String BUSINESS_CAPABILITY_ASSET_KEYS = "businessCapabilityAssetKeys";
    public static final String USER_ID = "userId";
    public static final String CLIENT_TYPE = "clientType";
    public static final String REVIEWED_DEMO_APPROVED = "reviewedDemoApproved";

    private TrustedToolContext() {
    }

    /**
     * 合并普通业务上下文和 Agent 宿主提供的可信运行事实。
     *
     * <p>当宿主没有提供发布环境时保持该 key 缺失，由真正依赖环境的 Tool 返回明确错误；已有不依赖
     * 环境的 Tool 不受影响。宿主提供非法值时原样透传，由领域消费者按统一错误码拒绝，禁止静默修正。
     */
    public static Map<String, Object> build(AgentEngineContext engineContext,
            Map<String, Object> bizToolContext) {
        Map<String, Object> context = new LinkedHashMap<>();
        if (bizToolContext != null) {
            context.putAll(bizToolContext);
        }
        context.remove(RELEASE_ENVIRONMENT);
        context.remove(TRACE_ID);
        context.remove(BUSINESS_CAPABILITY_ASSET_KEYS);
        context.remove(USER_ID);
        context.remove(CLIENT_TYPE);
        context.remove(REVIEWED_DEMO_APPROVED);
        String releaseEnvironment = engineContext == null ? null : engineContext.getReleaseEnvironment();
        if (StringUtils.isNotBlank(releaseEnvironment)) {
            context.put(RELEASE_ENVIRONMENT, releaseEnvironment);
        }
        String traceId = engineContext == null ? null : engineContext.getTraceId();
        if (StringUtils.isNotBlank(traceId)) {
            context.put(TRACE_ID, traceId);
        }
        Map<String, String> capabilityAssetKeys = engineContext == null
                ? null : engineContext.getBusinessCapabilityAssetKeys();
        if (capabilityAssetKeys != null && !capabilityAssetKeys.isEmpty()) {
            context.put(BUSINESS_CAPABILITY_ASSET_KEYS,
                    Map.copyOf(new LinkedHashMap<>(capabilityAssetKeys)));
        }
        Long userId = engineContext == null ? null : engineContext.getUserId();
        if (userId != null) {
            context.put(USER_ID, userId);
        }
        String clientType = engineContext == null || engineContext.getAgentContext() == null
                ? null : engineContext.getAgentContext().getClient();
        if (StringUtils.isNotBlank(clientType)) {
            context.put(CLIENT_TYPE, clientType);
        }
        return context;
    }

}
