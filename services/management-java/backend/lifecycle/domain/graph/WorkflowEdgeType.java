package dev.a2flow.management.lifecycle.domain.graph;

/**
 * Workflow Edge 类型枚举。
 *
 * <p>一期支持三种 Edge：
 * <ul>
 *   <li>NORMAL — 普通固定后继 Edge，连接上一个节点到下一个节点，不携带业务路由字段。</li>
 *   <li>ROUTING — Router Node 的候选出口 Edge，携带稳定业务 routeKey、业务说明和目标 nodeCode。</li>
 *   <li>PARALLEL — Fork Node 的固定分支出口 Edge，携带唯一且有序的 branchKey 和 branchOrder。</li>
 * </ul>
 *
 * <p>上游：WorkflowGraphAggregateParser（从 JSON 字段解析）。
 * <p>下游：WorkflowEdge 领域对象、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：拓扑验证、运行态 Edge 追踪、版本快照。
 */
public enum WorkflowEdgeType {

    NORMAL,
    ROUTING,
    PARALLEL;

    private static final String ERROR_UNKNOWN_EDGE_TYPE = "未知的 Workflow Edge 类型";

    /**
     * 从字符串解析 WorkflowEdgeType，未知值 fail closed。
     *
     * @param value JSON 中的 Edge 类型字符串
     * @return 对应枚举值
     * @throws IllegalArgumentException 若 value 为 null 或不在已知枚举集合中
     */
    public static WorkflowEdgeType fromString(String value) {
        if (value == null) {
            throw new IllegalArgumentException(ERROR_UNKNOWN_EDGE_TYPE + ": null");
        }
        for (WorkflowEdgeType type : values()) {
            if (type.name().equals(value)) {
                return type;
            }
        }
        throw new IllegalArgumentException(ERROR_UNKNOWN_EDGE_TYPE + ": " + value);
    }
}
