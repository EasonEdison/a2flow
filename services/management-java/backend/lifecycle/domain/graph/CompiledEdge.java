package dev.a2flow.management.lifecycle.domain.graph;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 编译后的不可变 Workflow Edge。
 *
 * <p>该对象保存固定连接、Router 候选或 Parallel 分支所需的最小稳定字段，供发布快照冻结图关系。
 * 通过 Builder 一次性构造，避免大参数构造器，同时保持字段只读和 Java 8 兼容。
 *
 * <p>上游：WorkflowCompiledPlanBuilder。下游：发布快照和 Adviser compiledPlan Reader。
 * <p>不负责：运行态路由选择、分支调度和 Join Arrival。
 */
public final class CompiledEdge {

    private final String edgeId;
    private final String sourceNodeCode;
    private final String targetNodeCode;
    private final WorkflowEdgeType edgeType;
    private final String routeKey;
    private final String description;
    private final String branchKey;
    private final Integer branchOrder;

    private CompiledEdge(Builder builder) {
        this.edgeId = builder.edgeId;
        this.sourceNodeCode = builder.sourceNodeCode;
        this.targetNodeCode = builder.targetNodeCode;
        this.edgeType = builder.edgeType;
        this.routeKey = builder.routeKey;
        this.description = builder.description;
        this.branchKey = builder.branchKey;
        this.branchOrder = builder.branchOrder;
    }

    public static Builder builder() {
        return new Builder();
    }

    public String getEdgeId() {
        return edgeId;
    }

    public String getSourceNodeCode() {
        return sourceNodeCode;
    }

    public String getTargetNodeCode() {
        return targetNodeCode;
    }

    public WorkflowEdgeType getEdgeType() {
        return edgeType;
    }

    /** Router 路由键仅在 ROUTING compiled edge 中输出。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getRouteKey() {
        return routeKey;
    }

    /** Router 候选描述仅在 ROUTING compiled edge 中输出。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getDescription() {
        return description;
    }

    /** Parallel 分支键仅在 PARALLEL compiled edge 中输出。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getBranchKey() {
        return branchKey;
    }

    /** Parallel 分支顺序仅在 PARALLEL compiled edge 中输出。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public Integer getBranchOrder() {
        return branchOrder;
    }

    /**
     * CompiledEdge 构建器，仅在编译阶段收集字段，build 后生成不可变对象。
     */
    public static final class Builder {
        private String edgeId;
        private String sourceNodeCode;
        private String targetNodeCode;
        private WorkflowEdgeType edgeType;
        private String routeKey;
        private String description;
        private String branchKey;
        private Integer branchOrder;

        private Builder() {
        }

        public Builder edgeId(String value) {
            this.edgeId = value;
            return this;
        }

        public Builder sourceNodeCode(String value) {
            this.sourceNodeCode = value;
            return this;
        }

        public Builder targetNodeCode(String value) {
            this.targetNodeCode = value;
            return this;
        }

        public Builder edgeType(WorkflowEdgeType value) {
            this.edgeType = value;
            return this;
        }

        public Builder routeKey(String value) {
            this.routeKey = value;
            return this;
        }

        public Builder description(String value) {
            this.description = value;
            return this;
        }

        public Builder branchKey(String value) {
            this.branchKey = value;
            return this;
        }

        public Builder branchOrder(Integer value) {
            this.branchOrder = value;
            return this;
        }

        public CompiledEdge build() {
            return new CompiledEdge(this);
        }
    }
}
