package dev.a2flow.management.lifecycle.domain.graph;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 节点领域基类。
 *
 * <p>所有节点类型（SKILL / ROUTER / PARALLEL_FORK / PARALLEL_JOIN / SUMMARY）共享
 * {@code nodeCode}（在 Workflow 范围内稳定唯一的节点标识）和 {@code nodeType}（决定
 * 节点语义和子类字段集）两个字段，其余字段由具体子类各自持有。
 *
 * <p>上游：WorkflowGraphAggregateParser（根据 nodeType 路由到具体子类实例化）。
 * <p>下游：WorkflowGraphAggregate（nodes 列表）、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：节点执行、拓扑编译、运行态生命周期。
 */
@Data
@Accessors(chain = true)
public abstract class WorkflowNode {

    private String nodeCode;
    private WorkflowNodeType nodeType;
    private String displayName;

    /** 可选展示名缺失时必须从 graph JSON 中省略，禁止序列化为显式 null。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getDisplayName() {
        return displayName;
    }
}
