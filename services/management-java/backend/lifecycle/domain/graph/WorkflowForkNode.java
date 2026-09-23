package dev.a2flow.management.lifecycle.domain.graph;

import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

/**
 * Workflow Parallel Fork 节点领域对象（nodeType=PARALLEL_FORK）。
 *
 * <p>Fork Node 是 Adviser 拥有的系统分发节点，按已发布的有序 branchKey/目标集合
 * 一次性创建所有固定分支，不调用模型。每个 Fork 必须通过 {@code matchingNodeCode}
 * 绑定唯一匹配的 PARALLEL_JOIN 节点；分支集合在发布时固定，禁止嵌套、动态增减或循环。
 *
 * <p>{@code joinPolicy} 一期固定为 {@code ALL_SUCCESS_OR_SKIPPED}，解析时强制校验。
 * {@code maxParallelism} 控制同一 Run 内最大并行分支数（正整数）。
 *
 * <p>上游：WorkflowGraphAggregateParser（nodeType=PARALLEL_FORK 时路由到此类）。
 * <p>下游：WorkflowGraphAggregate（nodes 列表）、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：并行执行调度、Join Arrival 幂等记录、分支 Attempt 创建。
 */
@Data
@EqualsAndHashCode(callSuper = true)
@Accessors(chain = true)
public class WorkflowForkNode extends WorkflowNode {

    private String matchingNodeCode;
    private String joinPolicy;
    private int maxParallelism;
}
