package dev.a2flow.management.lifecycle.domain.graph;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow Edge 领域对象。
 *
 * <p>Edge 描述 Workflow 图中两个节点间的有向连接。公共字段包括：{@code edgeId}（Edge 在
 * Workflow 范围内的稳定唯一标识）、{@code sourceNodeCode}、{@code targetNodeCode}、
 * {@code edgeType}。
 *
 * <p>按 edgeType 的额外字段：
 * <ul>
 *   <li>NORMAL — 无额外字段。</li>
 *   <li>ROUTING — {@code routeKey}（Router 本地唯一业务路由键）和 {@code description}
 *       （供模型理解的业务说明，非空）。</li>
 *   <li>PARALLEL — {@code branchKey}（Fork 本地唯一分支键）和 {@code branchOrder}
 *       （有序整数，决定分支确定性合并顺序）。</li>
 * </ul>
 *
 * <p>上游：WorkflowGraphAggregateParser（从 JSON {@code edges} 数组中解析每条 Edge）。
 * <p>下游：WorkflowGraphAggregate（edges 列表）、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：运行态 Edge 追踪、分支 Arrival 幂等记录、Route Decision 计算。
 */
@Data
@Accessors(chain = true)
public class WorkflowEdge {

    private String edgeId;
    private String sourceNodeCode;
    private String targetNodeCode;
    private WorkflowEdgeType edgeType;

    private String routeKey;
    private String description;

    private String branchKey;
    private Integer branchOrder;

    /** ROUTING 之外的 Edge 必须省略 routeKey，不得在 exact-field JSON 中输出显式 null。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getRouteKey() {
        return routeKey;
    }

    /** ROUTING 之外的 Edge 必须省略 description，不得在 exact-field JSON 中输出显式 null。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getDescription() {
        return description;
    }

    /** PARALLEL 之外的 Edge 必须省略 branchKey，不得在 exact-field JSON 中输出显式 null。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getBranchKey() {
        return branchKey;
    }

    /** PARALLEL 之外的 Edge 必须省略 branchOrder，不得在 exact-field JSON 中输出显式 null。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public Integer getBranchOrder() {
        return branchOrder;
    }
}
