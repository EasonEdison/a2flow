package dev.a2flow.management.event;

import lombok.Getter;

/**
 * SkillFactory AI Coding 内部流式事件基类。
 *
 * <p>该模型是 AI Coding Chat 的业务协议，不依赖通用运行时事件对象。
 * 上游由 `AiCodingStreamEventFactory` 创建，下游先按具体子类编码成结构化 envelope；
 * 需要兼容公共引擎接口时，由包外 bridge 负责转换。
 */
@Getter
public abstract sealed class AiCodingStreamEvent permits AiCodingModelContentEvent, AiCodingRuntimePayloadEvent {

    private final String eventType;
    private final String eventId;
    private final String source;
    private final String messageId;
    private final String runId;
    private final String threadId;
    private final String conversationId;
    private final String traceId;
    private final String content;
    private final long timestamp;
    private final long answerAgentId;

    protected AiCodingStreamEvent(AiCodingStreamEventMetadata metadata) {
        this.eventType = metadata.getEventType();
        this.eventId = metadata.getEventId();
        this.source = metadata.getSource();
        this.messageId = metadata.getMessageId();
        this.runId = metadata.getRunId();
        this.threadId = metadata.getThreadId();
        this.conversationId = metadata.getConversationId();
        this.traceId = metadata.getTraceId();
        this.content = metadata.getContent();
        this.timestamp = metadata.getTimestamp();
        this.answerAgentId = metadata.getAnswerAgentId();
    }
}
