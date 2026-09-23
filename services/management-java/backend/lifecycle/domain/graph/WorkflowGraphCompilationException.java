package dev.a2flow.management.lifecycle.domain.graph;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Workflow 图编译失败异常。
 *
 * <p>该异常由 WorkflowCompiledPlanBuilder 在发布前校验失败时抛出，向上游提供稳定错误码、
 * nodeCode、edgeId 和环路路径等定位信息。异常不保存 Prompt、草稿 payload 或其他敏感内容。
 *
 * <p>上游：WorkflowCompiledPlanBuilder。下游：控制面 API 和发布门禁的类型化错误映射。
 * <p>不负责：错误响应序列化、日志脱敏策略和运行态故障处理。
 */
public class WorkflowGraphCompilationException extends IllegalArgumentException {

    private static final long serialVersionUID = 1L;

    private final String errorCode;
    private final String nodeCode;
    private final String edgeId;
    private final String fieldPath;
    private final List<String> cyclePath;

    public WorkflowGraphCompilationException(
            String errorCode, String message, String nodeCode, String edgeId, List<String> cyclePath) {
        this(errorCode, message, nodeCode, edgeId, null, cyclePath);
    }

    public WorkflowGraphCompilationException(String errorCode, String message, String nodeCode,
            String edgeId, String fieldPath, List<String> cyclePath) {
        super(message);
        this.errorCode = errorCode;
        this.nodeCode = nodeCode;
        this.edgeId = edgeId;
        this.fieldPath = fieldPath;
        this.cyclePath = cyclePath == null
                ? Collections.<String>emptyList()
                : Collections.unmodifiableList(new ArrayList<>(cyclePath));
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getNodeCode() {
        return nodeCode;
    }

    public String getEdgeId() {
        return edgeId;
    }

    public String getFieldPath() {
        return fieldPath;
    }

    public List<String> getCyclePath() {
        return cyclePath;
    }
}
