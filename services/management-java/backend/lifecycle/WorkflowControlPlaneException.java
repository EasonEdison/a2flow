package dev.a2flow.management.lifecycle;

import lombok.Getter;

/**
 * Workflow 控制面稳定领域异常。
 *
 * <p>上游 Workflow 配置、分页和候选查询在可预期的失败关闭分支构造本异常；下游统一分发器按
 * errorCode、workflowCode 和 fieldPath 输出机器可读错误。该异常不承载 KConf 原文、SQL 或草稿内容。
 *
 * <p>不负责未知系统异常包装、日志脱敏或 RPC 协议扩展。
 */
@Getter
public class WorkflowControlPlaneException extends IllegalStateException {

    private static final long serialVersionUID = 1L;

    private final String errorCode;
    private final String workflowCode;
    private final String fieldPath;

    public WorkflowControlPlaneException(String errorCode, String message,
            String workflowCode, String fieldPath) {
        super(message);
        this.errorCode = errorCode;
        this.workflowCode = workflowCode;
        this.fieldPath = fieldPath;
    }

    public WorkflowControlPlaneException(String errorCode, String message,
            String workflowCode, String fieldPath, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
        this.workflowCode = workflowCode;
        this.fieldPath = fieldPath;
    }
}
