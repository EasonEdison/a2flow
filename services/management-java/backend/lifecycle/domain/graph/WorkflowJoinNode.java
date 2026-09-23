package dev.a2flow.management.lifecycle.domain.graph;

import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

/**
 * Workflow Parallel Join 节点领域对象（nodeType=PARALLEL_JOIN）。
 *
 * <p>Join Node 是 Adviser 拥有的系统汇合节点，等待匹配 Fork 的全部固定分支成功
 * 或被合法跳过后，再且仅再放行一次唯一后继。通过 {@code matchingNodeCode} 引用
 * 对应的 PARALLEL_FORK 节点，两者在 Workflow 编译时必须成对出现。
 *
 * <p>{@code joinPolicy} 一期固定为 {@code ALL_SUCCESS_OR_SKIPPED}，解析时强制校验。
 *
 * <p>上游：WorkflowGraphAggregateParser（nodeType=PARALLEL_JOIN 时路由到此类）。
 * <p>下游：WorkflowGraphAggregate（nodes 列表）、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：Join Arrival 幂等去重、后继 READY 创建、JOIN_ARRIVAL RunItem 写入。
 */
@Data
@EqualsAndHashCode(callSuper = true)
@Accessors(chain = true)
public class WorkflowJoinNode extends WorkflowNode {

    private String matchingNodeCode;
    private String joinPolicy;
}
