package dev.a2flow.management.lifecycle.domain;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 可选择的 Skill 稳定身份投影。
 *
 * <p>该对象只向配置控制面返回稳定 {@code skillCode} 和展示名称，不携带 Skill 版本、
 * Build、包内容、工作区路径或发布来源。上游由 WorkflowSpecialistSkillSelector 根据
 * Workflow 绑定专员和 Skill 当前存在性组装；店长返回全部 Skill，其他专员按关系隔离，不读取
 * 操作者对 Skill 的 VIEW 权限。下游供 M 端 Skill 下拉选择。
 *
 * <p>不负责：Skill 内容复制、版本锁定、发布状态解析和 Workflow 运行时执行。
 */
@Data
@Accessors(chain = true)
public class WorkflowSkillCandidateView {

    private String skillCode;
    private String displayName;
    private String description;
    private String status;
}
