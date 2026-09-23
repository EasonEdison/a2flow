package dev.a2flow.management.event;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

import lombok.Getter;

/**
 * AI Coding 模型内容块的基类。
 *
 * <p>该模型只表达大模型返回或选择的内容，包括最终正文、可见思考摘要、工具调用意图和受控业务意图。
 * 工具结果、patch、审批、业务交互卡片、observation、usage 和 error 都不是模型内容块，必须走运行态
 * payload 事件。该类只位于 SkillFactory 包内，不污染通用 Agent runtime 模型。
 */
@Getter
@JsonTypeInfo(use = JsonTypeInfo.Id.NAME, include = JsonTypeInfo.As.EXISTING_PROPERTY, property = "type",
        visible = true)
@JsonSubTypes({
        @JsonSubTypes.Type(value = AiCodingTextBlock.class, name = AiCodingModelContentBlock.TYPE_TEXT),
        @JsonSubTypes.Type(value = AiCodingThinkingBlock.class, name = AiCodingModelContentBlock.TYPE_THINKING),
        @JsonSubTypes.Type(value = AiCodingToolUseBlock.class, name = AiCodingModelContentBlock.TYPE_TOOL_USE),
        @JsonSubTypes.Type(value = AiCodingAgentIntentBlock.class, name = AiCodingModelContentBlock.TYPE_AGENT_INTENT)
})
public abstract sealed class AiCodingModelContentBlock
        permits AiCodingTextBlock, AiCodingThinkingBlock, AiCodingToolUseBlock, AiCodingAgentIntentBlock {

    public static final String TYPE_TEXT = "TEXT";
    public static final String TYPE_THINKING = "THINKING";
    public static final String TYPE_TOOL_USE = "TOOL_USE";
    public static final String TYPE_AGENT_INTENT = "AGENT_INTENT";

    private final String type;
    private String blockId;

    protected AiCodingModelContentBlock(String type) {
        this.type = type;
    }

    /**
     * 设置当前 block 的稳定 id，用于前端按 assistant turn 聚合增量。
     */
    public AiCodingModelContentBlock setBlockId(String blockId) {
        this.blockId = blockId;
        return this;
    }
}
