package dev.a2flow.management.lifecycle.domain.graph;

/**
 * 编译后的有序并行分支。
 *
 * <p>该对象冻结 branchKey、目标节点和稳定 branchOrder，确保发布内容及运行后聚合不受输入顺序影响。
 *
 * <p>上游：WorkflowCompiledPlanBuilder。下游：CompiledParallelDefinition。
 * <p>不负责：分支执行、容量控制和结果合并。
 */
public final class CompiledOrderedBranch {

    private final String branchKey;
    private final String targetNodeCode;
    private final int branchOrder;

    public CompiledOrderedBranch(String branchKey, String targetNodeCode, int branchOrder) {
        this.branchKey = branchKey;
        this.targetNodeCode = targetNodeCode;
        this.branchOrder = branchOrder;
    }

    public String getBranchKey() {
        return branchKey;
    }

    public String getTargetNodeCode() {
        return targetNodeCode;
    }

    public int getBranchOrder() {
        return branchOrder;
    }
}
