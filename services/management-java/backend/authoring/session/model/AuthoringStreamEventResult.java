package dev.a2flow.management.authoring.session.model;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Authoring Chat 结构化流式事件返回模型。
 *
 * <p>字段与 AI Coding stream envelope 对齐。recordId 是持久化事件的稳定身份，前端使用它把
 * 实时事件和历史回放事件精确合并，避免完成时整页重建或重复渲染。
 */
@Data
@Accessors(chain = true)
public class AuthoringStreamEventResult {

    private String recordId;
    private String schemaVersion;
    private String eventType;
    private String eventId;
    private String blockId;
    private String source;
    private String sessionId;
    private String workspaceId;
    private String invokeId;
    private String messageId;
    private String runId;
    private String conversationId;
    private String threadId;
    private String traceId;
    private String modelContentBlockJson;
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
    private boolean hasKnowledge;
    private long timestamp;
    private long answerAgentId;
}
