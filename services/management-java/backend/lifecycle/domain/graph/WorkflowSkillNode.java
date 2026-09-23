package dev.a2flow.management.lifecycle.domain.graph;

import com.fasterxml.jackson.annotation.JsonInclude;

import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

/**
 * Workflow Skill 节点领域对象（nodeType=SKILL）。
 *
 * <p>每个 Skill 节点引用稳定 {@code skillCode}，不复制 Skill 工作区内容、输出 Schema、
 * 版本 Build 或任何 PINNED/TRACK 字段。{@code nodePrompt} 描述该节点具体要让 Skill
 * 完成什么，只在节点执行时生效，不改写 Skill 发布内容。{@code controlPolicy} 保存
 * 该节点级别的执行控制策略（当前只含 allowSkip）。可选 {@code quickTriggerMessage}
 * 仅是用户主动点击后发送到会话的展示元数据，不属于节点执行 Prompt。
 *
 * <p>上游：WorkflowGraphAggregateParser（nodeType=SKILL 时路由到此类）。
 * <p>下游：WorkflowGraphAggregate（nodes 列表）、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：Skill 内容读取、Skill 版本锁定、运行态 Session 创建、工作区文件操作。
 */
@Data
@EqualsAndHashCode(callSuper = true)
@Accessors(chain = true)
public class WorkflowSkillNode extends WorkflowNode {

    private String skillCode;
    private String nodePrompt;
    private WorkflowNodeControlPolicy controlPolicy;
    private String quickTriggerMessage;

    /** 可选一键触发消息缺失时从 graph JSON 省略，禁止冻结为显式 null。 */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public String getQuickTriggerMessage() {
        return quickTriggerMessage;
    }
}
