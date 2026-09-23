package dev.a2flow.management.event;

import java.util.HashMap;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.support.JsonSupport;

/**
 * AI Coding 流式 envelope 编码器。
 *
 * <p>当前 KRPC/SSE 传输仍复用兼容 content 字段。该编码器只在 SkillFactory
 * AI Coding 包内组装结构化 envelope，避免修改 gateway 转换器或普通 ReAct 链路。
 */
public final class AiCodingStreamEnvelopeCodec {

    public static final String SCHEMA_VERSION = "skill-factory.agent-stream-event/v1";

    private static final String FIELD_SCHEMA_VERSION = "schemaVersion";
    private static final String FIELD_EVENT_TYPE = "eventType";
    private static final String FIELD_EVENT_ID = "eventId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_THREAD_ID = "threadId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String FIELD_BLOCK_ID = "blockId";
    private static final String FIELD_SOURCE = "source";
    private static final String FIELD_MODEL_CONTENT_BLOCK = "modelContentBlock";
    private static final String FIELD_PAYLOAD_TYPE = "payloadType";
    private static final String FIELD_PAYLOAD_JSON = "payloadJson";
    private static final String FIELD_PAYLOAD = "payload";
    private static final String FIELD_CONTENT = "content";
    private static final String FIELD_TOOL_CALL_ID = "toolCallId";
    private static final String FIELD_TOOL_NAME = "toolName";
    private static final String FIELD_TOOL_ARGS = "toolArgs";
    private static final String FIELD_TOOL_SUCCESS = "toolSuccess";
    private static final String FIELD_TOKEN_COUNT = "tokenCount";
    private static final String FIELD_ENTER_TOKEN_COUNT = "enterTokenCount";
    private static final String FIELD_OUTPUT_TOKEN_COUNT = "outputTokenCount";
    private static final String FIELD_TIMESTAMP = "timestamp";
    private static final String FIELD_ANSWER_AGENT_ID = "answerAgentId";
    private static final String FIELD_HAS_KNOWLEDGE = "hasKnowledge";

    private AiCodingStreamEnvelopeCodec() {
    }

    /**
     * 编码模型内容事件。
     */
    public static String modelContent(AiCodingStreamEnvelope envelope) {
        Map<String, Object> content = baseEnvelope(envelope);
        if (envelope.getModelContentBlock() != null) {
            content.put(FIELD_MODEL_CONTENT_BLOCK, envelope.getModelContentBlock());
        }
        return JsonSupport.toJSON(content);
    }

    /**
     * 编码运行态 payload 事件。
     */
    public static String runtimePayload(AiCodingStreamEnvelope envelope) {
        Map<String, Object> content = baseEnvelope(envelope);
        putIfNotBlank(content, FIELD_PAYLOAD_TYPE, envelope.getPayloadType());
        putIfNotBlank(content, FIELD_PAYLOAD_JSON, envelope.getPayloadJson());
        Object payload = parsePayload(envelope.getPayloadJson());
        if (payload != null) {
            content.put(FIELD_PAYLOAD, payload);
        }
        return JsonSupport.toJSON(content);
    }

    private static Map<String, Object> baseEnvelope(AiCodingStreamEnvelope envelope) {
        Map<String, Object> content = new HashMap<>();
        content.put(FIELD_SCHEMA_VERSION, SCHEMA_VERSION);
        putIfNotBlank(content, FIELD_EVENT_TYPE, envelope.getEventType());
        putIfNotBlank(content, FIELD_EVENT_ID, envelope.getEventId());
        putIfNotBlank(content, FIELD_MESSAGE_ID, envelope.getMessageId());
        putIfNotBlank(content, FIELD_RUN_ID, envelope.getRunId());
        putIfNotBlank(content, FIELD_THREAD_ID, envelope.getThreadId());
        putIfNotBlank(content, FIELD_CONVERSATION_ID, envelope.getConversationId());
        putIfNotBlank(content, FIELD_TRACE_ID, envelope.getTraceId());
        putIfNotBlank(content, FIELD_BLOCK_ID, envelope.getBlockId());
        putIfNotBlank(content, FIELD_SOURCE, envelope.getSource());
        putIfNotBlank(content, FIELD_CONTENT, envelope.getContent());
        putIfNotBlank(content, FIELD_TOOL_CALL_ID, envelope.getToolCallId());
        putIfNotBlank(content, FIELD_TOOL_NAME, envelope.getToolName());
        putIfNotBlank(content, FIELD_TOOL_ARGS, envelope.getToolArgs());
        content.put(FIELD_TOOL_SUCCESS, envelope.isToolSuccess());
        content.put(FIELD_TOKEN_COUNT, envelope.getTokenCount());
        content.put(FIELD_ENTER_TOKEN_COUNT, envelope.getEnterTokenCount());
        content.put(FIELD_OUTPUT_TOKEN_COUNT, envelope.getOutputTokenCount());
        content.put(FIELD_TIMESTAMP, envelope.getTimestamp());
        content.put(FIELD_ANSWER_AGENT_ID, envelope.getAnswerAgentId());
        content.put(FIELD_HAS_KNOWLEDGE, envelope.isHasKnowledge());
        return content;
    }

    private static Object parsePayload(String payloadJson) {
        if (StringUtils.isBlank(payloadJson)) {
            return null;
        }
        try {
            return JsonSupport.fromJSON(payloadJson, Object.class);
        } catch (Exception ignored) {
            return null;
        }
    }

    private static void putIfNotBlank(Map<String, Object> content, String key, String value) {
        if (StringUtils.isNotBlank(value)) {
            content.put(key, value);
        }
    }
}
