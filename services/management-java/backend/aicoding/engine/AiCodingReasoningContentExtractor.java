package dev.a2flow.management.aicoding.engine;

import java.util.Map;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.messages.AssistantMessage;

/**
 * SkillFactory 模型 reasoning metadata 提取器。
 *
 * <p>该工具只在模型流适配层读取 Wanqing / Spring AI message metadata 中的
 * `reasoningContent` 或 `reasoning_content`，供 DeepSeek 和 Claude 适配器复用。它不扫描正文，
 * 不判断模型厂商，也不把普通回答转换成思考内容。
 */
final class AiCodingReasoningContentExtractor {

    private static final String FIELD_REASONING_CONTENT = "reasoningContent";
    private static final String FIELD_REASONING_CONTENT_SNAKE = "reasoning_content";
    private static final int MAX_REASONING_SCAN_DEPTH = 2;

    private AiCodingReasoningContentExtractor() {
    }

    static String extract(AssistantMessage message) {
        if (message == null || MapUtils.isEmpty(message.getMetadata())) {
            return StringUtils.EMPTY;
        }
        Object reasoningContent = findReasoningValue(message.getMetadata(), 0);
        return reasoningContent == null ? StringUtils.EMPTY
                : StringUtils.defaultString(String.valueOf(reasoningContent));
    }

    private static Object findReasoningValue(Object value, int depth) {
        if (value == null || depth > MAX_REASONING_SCAN_DEPTH || !(value instanceof Map<?, ?> map)) {
            return null;
        }
        Object directValue = map.get(FIELD_REASONING_CONTENT);
        if (directValue == null) {
            directValue = map.get(FIELD_REASONING_CONTENT_SNAKE);
        }
        if (directValue != null) {
            return directValue;
        }
        for (Object child : map.values()) {
            Object childValue = findReasoningValue(child, depth + 1);
            if (childValue != null) {
                return childValue;
            }
        }
        return null;
    }
}
