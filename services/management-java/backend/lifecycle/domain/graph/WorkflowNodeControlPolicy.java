package dev.a2flow.management.lifecycle.domain.graph;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow Skill 节点控制策略。
 *
 * <p>目前只包含 {@code allowSkip} 一个布尔字段，控制当前 Skill 节点在执行失败或超时时
 * 是否允许被人工 Skip。该策略与 Skill 内容和版本无关，属于 Workflow 配置层独立维护的
 * 控制语义。
 *
 * <p>上游：WorkflowGraphAggregateParser（从 JSON {@code controlPolicy} 子对象解析）。
 * <p>下游：WorkflowSkillNode、WorkflowCompiledPlanBuilder（§3.4，本类不负责实现）。
 * <p>不负责：执行调度、Skip 实际触发逻辑、运行态状态管理。
 */
@Data
@Accessors(chain = true)
public class WorkflowNodeControlPolicy {

    private Boolean allowSkip;
}
