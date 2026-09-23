package dev.a2flow.management.aicoding.engine;

import java.util.Collections;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * SkillFactory AI Coding 默认 Spring AI 流式协议适配器。
 *
 * <p>该实现只读取 Spring AI 标准字段：`AssistantMessage.getText()` 作为正文增量、
 * `AssistantMessage.getToolCalls()` 作为工具调用增量、`ChatResponse.metadata.usage`
 * 作为 token 统计。它作为兜底适配器使用，不解析任何厂商私有 reasoning 字段。
 */
@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class DefaultAiCodingModelStreamAdapter implements AiCodingModelStreamAdapter {

    @Override
    public boolean supports(String modelName, ChatResponse chatResponse) {
        return true;
    }

    /**
     * 解析 Spring AI 标准流式响应。
     */
    @Override
    public AiCodingModelStreamDelta parse(ChatResponse chatResponse) {
        AiCodingModelStreamDelta delta = new AiCodingModelStreamDelta();
        fillUsage(chatResponse, delta);
        if (chatResponse == null || chatResponse.getResult() == null
                || chatResponse.getResult().getOutput() == null) {
            return delta;
        }
        AssistantMessage message = chatResponse.getResult().getOutput();
        delta.setAssistantMessage(message)
                .setTextContent(StringUtils.defaultString(message.getText()))
                .setToolCalls(message.getToolCalls() == null ? Collections.emptyList() : message.getToolCalls())
                .setFinishReason(chatResponse.getResult().getMetadata() == null ? StringUtils.EMPTY
                        : StringUtils.defaultString(chatResponse.getResult().getMetadata().getFinishReason()));
        return delta;
    }

    /**
     * 抽取标准 usage 统计。这里保持和原 AI Coding 统计口径一致：每个 chunk 的 prompt/completion
     * token 都累加到本轮会话的 usage 里。
     */
    protected void fillUsage(ChatResponse chatResponse, AiCodingModelStreamDelta delta) {
        if (chatResponse == null || chatResponse.getMetadata() == null
                || chatResponse.getMetadata().getUsage() == null) {
            return;
        }
        int enterTokens = chatResponse.getMetadata().getUsage().getPromptTokens();
        int outputTokens = chatResponse.getMetadata().getUsage().getCompletionTokens();
        delta.setEnterTokens(enterTokens)
                .setOutputTokens(outputTokens)
                .setTotalTokens(enterTokens + outputTokens);
    }
}
