package dev.a2flow.management.aicoding.engine;

import java.util.Collections;
import java.util.List;

import org.springframework.ai.chat.messages.AssistantMessage;

/**
 * SkillFactory AI Coding 内部统一模型流增量。
 *
 * <p>不同模型厂商在流式返回里对正文、reasoning、tool call、usage 和结束信息的承载位置并不一致。
 * 该对象是适配器输出给 `AiCodingReActEngine` 的统一形态，只在 SkillFactory AI Coding 链路内部使用，
 * 不作为前端或公共 Agent runtime 协议。上游由具体 `AiCodingModelStreamAdapter` 按厂商协议解析，
 * 下游由 AI Coding engine 继续转换成 `AiCodingStreamEvent`。
 */
public class AiCodingModelStreamDelta {

    private AssistantMessage assistantMessage;
    private String textContent = "";
    private String reasoningContent = "";
    private List<AssistantMessage.ToolCall> toolCalls = Collections.emptyList();
    private int totalTokens;
    private int enterTokens;
    private int outputTokens;
    private String finishReason = "";

    public AssistantMessage getAssistantMessage() {
        return assistantMessage;
    }

    public AiCodingModelStreamDelta setAssistantMessage(AssistantMessage assistantMessage) {
        this.assistantMessage = assistantMessage;
        return this;
    }

    public String getTextContent() {
        return textContent;
    }

    public AiCodingModelStreamDelta setTextContent(String textContent) {
        this.textContent = textContent;
        return this;
    }

    public String getReasoningContent() {
        return reasoningContent;
    }

    public AiCodingModelStreamDelta setReasoningContent(String reasoningContent) {
        this.reasoningContent = reasoningContent;
        return this;
    }

    public List<AssistantMessage.ToolCall> getToolCalls() {
        return toolCalls;
    }

    public AiCodingModelStreamDelta setToolCalls(List<AssistantMessage.ToolCall> toolCalls) {
        this.toolCalls = toolCalls == null ? Collections.emptyList() : toolCalls;
        return this;
    }

    public int getTotalTokens() {
        return totalTokens;
    }

    public AiCodingModelStreamDelta setTotalTokens(int totalTokens) {
        this.totalTokens = totalTokens;
        return this;
    }

    public int getEnterTokens() {
        return enterTokens;
    }

    public AiCodingModelStreamDelta setEnterTokens(int enterTokens) {
        this.enterTokens = enterTokens;
        return this;
    }

    public int getOutputTokens() {
        return outputTokens;
    }

    public AiCodingModelStreamDelta setOutputTokens(int outputTokens) {
        this.outputTokens = outputTokens;
        return this;
    }

    public String getFinishReason() {
        return finishReason;
    }

    public AiCodingModelStreamDelta setFinishReason(String finishReason) {
        this.finishReason = finishReason;
        return this;
    }
}
