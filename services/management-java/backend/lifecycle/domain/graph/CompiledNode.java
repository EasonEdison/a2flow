package dev.a2flow.management.lifecycle.domain.graph;

import com.fasterxml.jackson.annotation.JsonGetter;
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * 编译后的不可变 Workflow 节点。
 *
 * <p>所有节点只保存公共身份字段。Skill 节点额外保存稳定 skillCode、nodePrompt 和 allowSkip；
 * Router、Fork、Join 与 Summary 的专属执行字段分别由 compiledPlan 的专属定义承载，
 * 不混入 Skill 节点输出或 Skill 节点 canonical digest。
 *
 * <p>上游：WorkflowCompiledPlanBuilder。下游：发布快照和 Adviser compiledPlan Reader。
 * <p>不负责：节点执行、Skill 加载和运行态状态迁移。
 */
public final class CompiledNode {

    private final String nodeCode;
    private final WorkflowNodeType nodeType;
    private final String displayName;
    private final String skillCode;
    private final String nodePrompt;
    private final boolean allowSkip;

    private CompiledNode(Builder builder) {
        this.nodeCode = builder.nodeCode;
        this.nodeType = builder.nodeType;
        this.displayName = builder.displayName;
        this.skillCode = builder.skillCode;
        this.nodePrompt = builder.nodePrompt;
        this.allowSkip = builder.allowSkip;
    }

    static Builder builder() {
        return new Builder();
    }

    public String getNodeCode() {
        return nodeCode;
    }

    public WorkflowNodeType getNodeType() {
        return nodeType;
    }

    /** 可选展示名缺失时必须从 compiledPlan JSON 中省略，禁止序列化为显式 null。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getDisplayName() {
        return displayName;
    }

    /** Skill 专属标识只在 Skill compiled node 中输出。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getSkillCode() {
        return skillCode;
    }

    /** Skill 专属 Prompt 只在 Skill compiled node 中输出。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getNodePrompt() {
        return nodePrompt;
    }

    @JsonIgnore
    public boolean isAllowSkip() {
        return allowSkip;
    }

    /**
     * Skill 的 allowSkip 即使为 false 也必须冻结；系统节点则不得产生同名 JSON 字段。
     */
    @JsonGetter("allowSkip")
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public Boolean getAllowSkipForJson() {
        return nodeType == WorkflowNodeType.SKILL ? Boolean.valueOf(allowSkip) : null;
    }

    /**
     * CompiledNode 包内构建器，仅允许图编译器按校验后的节点创建不可变对象。
     */
    static final class Builder {
        private String nodeCode;
        private WorkflowNodeType nodeType;
        private String displayName;
        private String skillCode;
        private String nodePrompt;
        private boolean allowSkip;

        private Builder() {
        }

        Builder nodeCode(String value) {
            this.nodeCode = value;
            return this;
        }

        Builder nodeType(WorkflowNodeType value) {
            this.nodeType = value;
            return this;
        }

        Builder displayName(String value) {
            this.displayName = value;
            return this;
        }

        Builder skillCode(String value) {
            this.skillCode = value;
            return this;
        }

        Builder nodePrompt(String value) {
            this.nodePrompt = value;
            return this;
        }

        Builder allowSkip(boolean value) {
            this.allowSkip = value;
            return this;
        }

        CompiledNode build() {
            if (nodeCode == null || nodeType == null) {
                throw new IllegalStateException("CompiledNode公共身份字段不完整");
            }
            if (nodeType == WorkflowNodeType.SKILL
                    && (skillCode == null || nodePrompt == null)) {
                throw new IllegalStateException("CompiledNode Skill字段不完整");
            }
            if (nodeType != WorkflowNodeType.SKILL
                    && (skillCode != null || nodePrompt != null || allowSkip)) {
                throw new IllegalStateException("系统节点不得携带Skill专属字段");
            }
            return new CompiledNode(this);
        }
    }
}
