package dev.a2flow.management.lifecycle.domain.graph;

import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

/**
 * Workflow Summary 节点领域对象（nodeType=SUMMARY）。
 *
 * <p>Summary Node 是所有业务节点结束后执行的系统总结步骤，在 Workflow 图中有且只有一个，
 * {@code nodeCode} 固定为 {@code __summary__}（解析时强制校验）。{@code prompt} 由配置者
 * 填写，说明如何从全部节点的结构化 Observation 生成最终摘要。
 *
 * <p>{@code allowSkip} 对 Summary Node 固定为 {@code false}，解析时如果 JSON 中明确
 * 提供了 {@code allowSkip=true} 则 fail closed 拒绝。
 *
 * <p>上游：WorkflowGraphAggregateParser（nodeType=SUMMARY 时路由到此类）。
 * <p>下游：WorkflowGraphAggregate（nodes 列表）、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：总结模型调用、FINAL_CONCLUSION Observation 写入、运行结果投影。
 */
@Data
@EqualsAndHashCode(callSuper = true)
@Accessors(chain = true)
public class WorkflowSummaryNode extends WorkflowNode {

    private String prompt;
    private boolean allowSkip;
}
