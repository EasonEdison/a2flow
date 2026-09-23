package dev.a2flow.management.lifecycle.domain.graph;

/**
 * Workflow 节点类型枚举。
 *
 * <p>一期支持五种节点：
 * <ul>
 *   <li>SKILL — 业务 Skill 执行步骤，引用稳定 skillCode，不复制 Skill 内容。</li>
 *   <li>ROUTER — Adviser 拥有的系统路由步骤，从已发布候选 routeKey 中选择唯一下一路径。</li>
 *   <li>PARALLEL_FORK — 系统分发节点，一次性创建所有固定分支，不调用模型。</li>
 *   <li>PARALLEL_JOIN — 系统汇合节点，等待全部固定分支成功或合法跳过后放行唯一后继。</li>
 *   <li>SUMMARY — 所有业务节点结束后执行的系统总结步骤，nodeCode 固定为 {@code __summary__}。</li>
 * </ul>
 *
 * <p>上游：WorkflowGraphAggregateParser（从 JSON 字段解析）。
 * <p>下游：WorkflowNode 子类、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：拓扑编译、运行态调度、版本快照。
 */
public enum WorkflowNodeType {

    SKILL,
    ROUTER,
    PARALLEL_FORK,
    PARALLEL_JOIN,
    SUMMARY;

    private static final String ERROR_UNKNOWN_NODE_TYPE = "未知的 Workflow 节点类型";

    /**
     * 从字符串解析 WorkflowNodeType，未知值 fail closed。
     *
     * @param value JSON 中的节点类型字符串
     * @return 对应枚举值
     * @throws IllegalArgumentException 若 value 为 null 或不在已知枚举集合中
     */
    public static WorkflowNodeType fromString(String value) {
        if (value == null) {
            throw new IllegalArgumentException(ERROR_UNKNOWN_NODE_TYPE + ": null");
        }
        for (WorkflowNodeType type : values()) {
            if (type.name().equals(value)) {
                return type;
            }
        }
        throw new IllegalArgumentException(ERROR_UNKNOWN_NODE_TYPE + ": " + value);
    }
}
