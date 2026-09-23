package dev.a2flow.management.event;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * AI Coding 结构化流事件 envelope。
 *
 * <p>该对象只在 SkillFactory 包内使用，最终会被编码为兼容传输字段，
 * 因此外层运行时不需要感知这些结构化字段。
 */
@Data
@Accessors(chain = true)
public class AiCodingStreamEnvelope {

    private String eventType;
    private String eventId;
    private String blockId;
    private String source;
    private String messageId;
    private String runId;
    private String threadId;
    private String conversationId;
    private String traceId;
    private AiCodingModelContentBlock modelContentBlock;
    private String payloadType;
    private String payloadJson;
    private String content;
    private String toolCallId;
    private String toolName;
    private String toolArgs;
    private boolean toolSuccess;
    private long tokenCount;
    private long enterTokenCount;
    private long outputTokenCount;
    private long timestamp;
    private long answerAgentId;
    private boolean hasKnowledge;
}
