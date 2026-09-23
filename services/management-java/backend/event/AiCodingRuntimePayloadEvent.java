package dev.a2flow.management.event;

import lombok.Getter;

/**
 * AI Coding 运行态 payload 事件。
 *
 * <p>该事件表达工具结果、patch 产物、审批请求、业务交互、observation、usage、error 和执行
 * trace 等系统事实。它不是模型内容 block；前端应按 `payloadType/payloadJson` 渲染，而不是解析
 * fallback `content`。
 */
@Getter
public final class AiCodingRuntimePayloadEvent extends AiCodingStreamEvent {

    private final String payloadType;
    private final String payloadJson;
    private final String toolCallId;
    private final String toolName;
    private final String toolArgs;
    private final boolean toolSuccess;
    private final int tokenCount;
    private final int enterTokenCount;
    private final int outputTokenCount;
    private final boolean hasKnowledge;

    public AiCodingRuntimePayloadEvent(AiCodingStreamEventMetadata metadata, AiCodingRuntimePayload runtimePayload) {
        super(metadata);
        this.payloadType = runtimePayload.getPayloadType();
        this.payloadJson = runtimePayload.getPayloadJson();
        this.toolCallId = runtimePayload.getToolCallId();
        this.toolName = runtimePayload.getToolName();
        this.toolArgs = runtimePayload.getToolArgs();
        this.toolSuccess = runtimePayload.isToolSuccess();
        this.tokenCount = runtimePayload.getTokenCount();
        this.enterTokenCount = runtimePayload.getEnterTokenCount();
        this.outputTokenCount = runtimePayload.getOutputTokenCount();
        this.hasKnowledge = runtimePayload.isHasKnowledge();
    }
}
