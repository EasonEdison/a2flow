package dev.a2flow.management.lifecycle.domain.graph;

import lombok.Getter;

/**
 * Workflow graph 输入数据的结构化校验异常。
 *
 * <p>解析器仅用该异常表达 JSON 语法、字段类型、必填字段、未知字段和领域数据约束错误；
 * 上游发布适配器据此拼接冻结 payload 根路径。异常只携带稳定错误码和字段路径，不保存原始 payload。
 */
@Getter
public class WorkflowGraphDataException extends IllegalArgumentException {

    private static final long serialVersionUID = 1L;

    private final String errorCode;
    private final String fieldPath;

    public WorkflowGraphDataException(String errorCode, String message, String fieldPath) {
        super(message);
        this.errorCode = errorCode;
        this.fieldPath = fieldPath;
    }

    public WorkflowGraphDataException(String errorCode, String message, String fieldPath, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
        this.fieldPath = fieldPath;
    }
}
