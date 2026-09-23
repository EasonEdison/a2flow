package dev.a2flow.management.event;

import lombok.Getter;

/**
 * AI Coding 模型内容事件。
 *
 * <p>该事件只包装 `AiCodingModelContentBlock`，用于正文、可见思考摘要、工具调用意图和受控
 * 业务意图。运行态事实必须使用 `AiCodingRuntimePayloadEvent`，不能塞进这里。
 */
@Getter
public final class AiCodingModelContentEvent extends AiCodingStreamEvent {

    private final String blockId;
    private final AiCodingModelContentBlock modelContentBlock;

    public AiCodingModelContentEvent(AiCodingStreamEventMetadata metadata, String blockId,
            AiCodingModelContentBlock modelContentBlock) {
        super(metadata);
        this.blockId = blockId;
        this.modelContentBlock = modelContentBlock;
    }
}
