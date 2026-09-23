package dev.a2flow.management.lifecycle.domain.graph;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 编译后的不可变并行组定义。
 *
 * <p>该对象冻结匹配 Fork/Join、稳定有序分支、固定 Join 策略和并发上限。
 *
 * <p>上游：WorkflowCompiledPlanBuilder。下游：CompiledPlan 和 Adviser 并行运行时。
 * <p>不负责：运行态 fan-out、Join Arrival 和 worker 容量管理。
 */
public final class CompiledParallelDefinition {

    private final String forkNodeCode;
    private final String joinNodeCode;
    private final List<CompiledOrderedBranch> orderedBranches;
    private final String joinPolicy;
    private final int maxParallelism;

    public CompiledParallelDefinition(String forkNodeCode, String joinNodeCode,
            List<CompiledOrderedBranch> orderedBranches, String joinPolicy, int maxParallelism) {
        if (orderedBranches == null) {
            throw new IllegalArgumentException("并行分支集合不能为空");
        }
        this.forkNodeCode = forkNodeCode;
        this.joinNodeCode = joinNodeCode;
        this.orderedBranches = Collections.unmodifiableList(new ArrayList<>(orderedBranches));
        this.joinPolicy = joinPolicy;
        this.maxParallelism = maxParallelism;
    }

    public String getForkNodeCode() {
        return forkNodeCode;
    }

    public String getJoinNodeCode() {
        return joinNodeCode;
    }

    public List<CompiledOrderedBranch> getOrderedBranches() {
        return orderedBranches;
    }

    public String getJoinPolicy() {
        return joinPolicy;
    }

    public int getMaxParallelism() {
        return maxParallelism;
    }
}
