package dev.a2flow.management.aicoding.engine;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * SkillFactory AI Coding DeepSeekV4Pro 流式协议适配器。
 *
 * <p>DeepSeekV4Pro 会把可展示 reasoning 放在 `reasoning_content`，Wanqing / Spring AI
 * 适配后也可能变成 `reasoningContent` 并挂在 message metadata 的不同层级里。该适配器只负责把
 * DeepSeek 的 reasoning 通道抽成 AI Coding 内部 `reasoningContent`，正文和 tool call 仍复用
 * 默认 Spring AI 解析。它不负责前端渲染，也不改变 patch、approval 或 observation 语义。
 */
@Component
@Order(0)
public class DeepSeekV4ProAiCodingModelStreamAdapter extends DefaultAiCodingModelStreamAdapter {

    private static final String MODEL_DEEPSEEK = "deepseek";
    @Override
    public boolean supports(String modelName, ChatResponse chatResponse) {
        return StringUtils.containsIgnoreCase(modelName, MODEL_DEEPSEEK)
                || StringUtils.isNotBlank(AiCodingReasoningContentExtractor.extract(
                        resolveAssistantMessage(chatResponse)));
    }

    /**
     * 解析 DeepSeekV4Pro reasoning 通道，并保持正文/tool/usage 的标准解析结果。
     */
    @Override
    public AiCodingModelStreamDelta parse(ChatResponse chatResponse) {
        AiCodingModelStreamDelta delta = super.parse(chatResponse);
        delta.setReasoningContent(AiCodingReasoningContentExtractor.extract(delta.getAssistantMessage()));
        return delta;
    }

    private AssistantMessage resolveAssistantMessage(ChatResponse chatResponse) {
        if (chatResponse == null || chatResponse.getResult() == null) {
            return null;
        }
        return chatResponse.getResult().getOutput();
    }

}
