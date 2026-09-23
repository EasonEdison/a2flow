package dev.a2flow.management.lifecycle.domain.graph;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import lombok.Getter;

/**
 * Workflow 图预览使用的稳定校验错误。
 *
 * <p>上游由解析器或编译器的类型化异常转换而来，下游由控制面预览接口以列表返回。该对象只暴露
 * 稳定错误码和最小定位字段，不携带原始 JSON、Prompt 或底层异常消息；执行编译仍直接抛异常并
 * 失败关闭，不消费本预览模型。
 */
@Getter
public class WorkflowGraphValidationError {

    private final String errorCode;
    private final String message;
    private final String fieldPath;
    private final String nodeCode;
    private final String edgeId;
    private final List<String> graphPath;

    public WorkflowGraphValidationError(String errorCode, String message, String fieldPath,
            String nodeCode, String edgeId, List<String> graphPath) {
        this.errorCode = errorCode;
        this.message = message;
        this.fieldPath = fieldPath;
        this.nodeCode = nodeCode;
        this.edgeId = edgeId;
        this.graphPath = graphPath == null
                ? Collections.emptyList()
                : Collections.unmodifiableList(new ArrayList<>(graphPath));
    }
}
