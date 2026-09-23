package dev.a2flow.management.lifecycle;

/**
 * Workflow Skill 引用校验失败异常。
 *
 * <p>该异常用于草稿保存以及后续公共发布 Build/Publish 门禁的统一后端重验，稳定携带错误码、
 * nodeCode、skillCode、Workflow 绑定专员和精确 fieldPath。Skill 不存在，或普通专员 Workflow 的
 * 当前 Skill 专员关系已移除时均失败关闭；店长 Workflow 仅要求 Skill 存在，不通过草稿、latest
 * 版本或历史关系降级。
 *
 * <p>上游：WorkflowSpecialistSkillSelector。下游：控制面 API 与公共发布 Adapter 的类型化错误映射。
 * <p>不负责：响应序列化、发布状态机和 Skill 内容读取。
 */
public class WorkflowSkillReferenceValidationException extends IllegalArgumentException {

    private static final long serialVersionUID = 1L;

    private final String errorCode;
    private final String nodeCode;
    private final String skillCode;
    private final String workflowSpecialistCode;
    private final String fieldPath;

    public WorkflowSkillReferenceValidationException(String errorCode, String message,
            String nodeCode, String skillCode, String workflowSpecialistCode, String fieldPath) {
        super(message);
        this.errorCode = errorCode;
        this.nodeCode = nodeCode;
        this.skillCode = skillCode;
        this.workflowSpecialistCode = workflowSpecialistCode;
        this.fieldPath = fieldPath;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getNodeCode() {
        return nodeCode;
    }

    public String getSkillCode() {
        return skillCode;
    }

    public String getWorkflowSpecialistCode() {
        return workflowSpecialistCode;
    }

    public String getFieldPath() {
        return fieldPath;
    }
}
