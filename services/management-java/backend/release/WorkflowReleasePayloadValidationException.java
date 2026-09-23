package dev.a2flow.management.release;

import lombok.Getter;

/**
 * Workflow 冻结发布 payload 的稳定校验异常。
 *
 * <p>上游 payload Adapter 在契约版本、快照身份或字段校验失败时构造；下游发布与公共依赖门禁按
 * errorCode、workflowCode 和 fieldPath 精确定位。本异常不承载完整 payload，也不处理系统故障。
 */
@Getter
public class WorkflowReleasePayloadValidationException extends IllegalStateException {

    private static final long serialVersionUID = 1L;

    private final String errorCode;
    private final String workflowCode;
    private final String fieldPath;

    public WorkflowReleasePayloadValidationException(String errorCode, String message,
            String workflowCode, String fieldPath) {
        super(message);
        this.errorCode = errorCode;
        this.workflowCode = workflowCode;
        this.fieldPath = fieldPath;
    }

    public WorkflowReleasePayloadValidationException(String errorCode, String message,
            String workflowCode, String fieldPath, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
        this.workflowCode = workflowCode;
        this.fieldPath = fieldPath;
    }
}
