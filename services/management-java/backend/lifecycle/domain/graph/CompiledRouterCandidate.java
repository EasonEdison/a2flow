package dev.a2flow.management.lifecycle.domain.graph;

/**
 * 编译后的 Router 候选项。
 *
 * <p>候选项冻结稳定 routeKey、业务说明和可信目标节点映射，供 Adviser 通过 routeKey 唯一选路。
 *
 * <p>上游：WorkflowCompiledPlanBuilder。下游：CompiledRouterDefinition。
 * <p>不负责：模型调用和 Route Decision 持久化。
 */
public final class CompiledRouterCandidate {

    private final String routeKey;
    private final String description;
    private final String targetNodeCode;

    public CompiledRouterCandidate(String routeKey, String description, String targetNodeCode) {
        this.routeKey = routeKey;
        this.description = description;
        this.targetNodeCode = targetNodeCode;
    }

    public String getRouteKey() {
        return routeKey;
    }

    public String getDescription() {
        return description;
    }

    public String getTargetNodeCode() {
        return targetNodeCode;
    }
}
