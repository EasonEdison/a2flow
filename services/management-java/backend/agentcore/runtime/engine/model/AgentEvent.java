package dev.a2flow.management.agentcore.runtime.engine.model;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.agentcore.api.enums.AgentEventType;

import lombok.Data;

/**

 * Created on 2026-04-23
 */
@Data
public class AgentEvent {
    private AgentEventType eventType;
    private String content;
    private String toolCallId;
    private String toolName;
    private String toolArgs;
    private boolean success;
    private long tokenCount;
    private long enterTokenCount;
    private long outputTokenCount;
    private long timestamp;
    private long answerAgentId;
    private boolean fullModelConv; // 代表该次event是一轮完整的模型对话内容
    private boolean hasKnowledge;

    public static AgentEvent error(long answerAgentId, String message) {
        AgentEvent agentEvent = new AgentEvent();
        agentEvent.setEventType(AgentEventType.ERROR);
        agentEvent.setContent(StringUtils.defaultString(message));
        agentEvent.setTimestamp(System.currentTimeMillis());
        agentEvent.setAnswerAgentId(answerAgentId);
        return agentEvent;
    }

    public static AgentEvent started(long answerAgentId) {
        AgentEvent agentEvent = new AgentEvent();
        agentEvent.setEventType(AgentEventType.STARTED);
        agentEvent.setTimestamp(System.currentTimeMillis());
        agentEvent.setAnswerAgentId(answerAgentId);
        return agentEvent;
    }

    public static AgentEvent thinkTextDelta(long answerAgentId, String content) {
        AgentEvent agentEvent = new AgentEvent();
        agentEvent.setEventType(AgentEventType.THINK_TEXT_DELTA);
        agentEvent.setContent(StringUtils.defaultString(content));
        agentEvent.setTimestamp(System.currentTimeMillis());
        agentEvent.setAnswerAgentId(answerAgentId);
        return agentEvent;
    }

    public static AgentEvent answerTextDelta(long answerAgentId, String content) {
        AgentEvent agentEvent = new AgentEvent();
        agentEvent.setEventType(AgentEventType.ANSWER_TEXT_DELTA);
        agentEvent.setContent(StringUtils.defaultString(content));
        agentEvent.setTimestamp(System.currentTimeMillis());
        agentEvent.setAnswerAgentId(answerAgentId);
        return agentEvent;
    }

    public static AgentEvent toolCall(long answerAgentId, String toolCallId, String toolName, String args) {
        AgentEvent agentEvent = new AgentEvent();
        agentEvent.setEventType(AgentEventType.TOOL_CALL);
        agentEvent.setToolCallId(StringUtils.defaultString(toolCallId));
        agentEvent.setToolName(StringUtils.defaultString(toolName));
        agentEvent.setToolArgs(StringUtils.defaultString(args));
        agentEvent.setTimestamp(System.currentTimeMillis());
        agentEvent.setAnswerAgentId(answerAgentId);
        return agentEvent;
    }

    public static AgentEvent toolResult(long answerAgentId, String toolCallId, String toolName, String result,
            boolean success) {
        AgentEvent agentEvent = new AgentEvent();
        agentEvent.setEventType(AgentEventType.TOOL_RESULT);
        agentEvent.setToolCallId(StringUtils.defaultString(toolCallId));
        agentEvent.setToolName(StringUtils.defaultString(toolName));
        agentEvent.setContent(StringUtils.defaultString(result));
        agentEvent.setSuccess(success);
        agentEvent.setTimestamp(System.currentTimeMillis());
        agentEvent.setAnswerAgentId(answerAgentId);
        return agentEvent;
    }

    public static AgentEvent toolResult(long answerAgentId, String toolCallId, String toolName, String result,
            boolean success, boolean hasKnowledge) {
        AgentEvent agentEvent = toolResult(answerAgentId, toolCallId, toolName, result, success);
        agentEvent.setHasKnowledge(hasKnowledge);
        return agentEvent;
    }

    public static AgentEvent usage(long answerAgentId, int tokenCount) {
        AgentEvent agentEvent = new AgentEvent();
        agentEvent.setEventType(AgentEventType.USAGE);
        agentEvent.setTokenCount(tokenCount);
        agentEvent.setTimestamp(System.currentTimeMillis());
        agentEvent.setAnswerAgentId(answerAgentId);
        return agentEvent;
    }

    public static AgentEvent usage(long answerAgentId, int tokenCount, int enterTokenCount, int outputTokenCount) {
        AgentEvent agentEvent = new AgentEvent();
        agentEvent.setEventType(AgentEventType.USAGE);
        agentEvent.setTokenCount(tokenCount);
        agentEvent.setEnterTokenCount(enterTokenCount);
        agentEvent.setOutputTokenCount(outputTokenCount);
        agentEvent.setTimestamp(System.currentTimeMillis());
        agentEvent.setAnswerAgentId(answerAgentId);
        return agentEvent;
    }

    public static AgentEvent completed(long answerAgentId) {
        AgentEvent agentEvent = new AgentEvent();
        agentEvent.setEventType(AgentEventType.COMPLETED);
        agentEvent.setTimestamp(System.currentTimeMillis());
        agentEvent.setAnswerAgentId(answerAgentId);
        return agentEvent;
    }



}
