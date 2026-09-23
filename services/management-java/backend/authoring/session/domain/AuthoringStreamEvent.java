package dev.a2flow.management.authoring.session.domain;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Authoring Chat 流式事件领域对象。
 *
 * <p>该对象保存 AI Coding 结构化流式协议的可回放事实。模型内容、运行态 payload 和兼容文本均
 * 使用明确字段持久化，不把整条事件压成黑盒 JSON；recordId 是历史回查与实时事件稳定合并的幂等身份。
 * 事件渲染和页面分层不属于该对象职责。
 */
@Data
@Accessors(chain = true)
public class AuthoringStreamEvent {

    private String recordId;
    private String sessionId;
    private String schemaVersion;
    private String eventType;
    private String eventId;
    private String blockId;
    private String source;
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
