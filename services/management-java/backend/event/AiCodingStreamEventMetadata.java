package dev.a2flow.management.event;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * AI Coding 流式事件公共元信息。
 *
 * <p>该对象只在 SkillFactory 内部传递 messageId、runId、traceId、source 等聚合字段，
 * 不承载模型正文、工具结果或 patch 业务数据。具体内容必须放到 `AiCodingModelContentEvent`
 * 或 `AiCodingRuntimePayloadEvent` 中，避免重新退回 `eventType + content` 黑盒协议。
 */
@Data
@Accessors(chain = true)
public class AiCodingStreamEventMetadata {

    private String eventType;
    private String eventId;
    private String source;
    private String messageId;
    private String runId;
    private String threadId;
    private String conversationId;
    private String traceId;
    private String content;
    private long timestamp;
    private long answerAgentId;
}
