package dev.a2flow.management.aicoding.engine;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * SkillFactory Claude-family 流式协议适配器。
 *
 * <p>正常路径优先读取 Wanqing / Spring AI 暴露的独立 reasoning metadata。仅当 Wanqing 偶发把
 * 可见思考降级到正文 `<think>...</think>` 时，本适配器才把标签内内容保留为 fallback reasoning，
 * 并从最终正文移除标签和思考内容。解析状态只活在单次模型调用中，支持开始/结束标签跨 chunk；
 * 本类不合成 Claude signature、redacted-thinking，也不负责事件展示或 Tool 执行。
 */
@Component
@Order(-100)
public class ClaudeAiCodingModelStreamAdapter extends DefaultAiCodingModelStreamAdapter {

    private static final String MODEL_CLAUDE = "claude";
    private static final String MODEL_ANTHROPIC = "anthropic";
    private static final String OPEN_THINK_TAG = "<think>";
    private static final String CLOSE_THINK_TAG = "</think>";

    @Override
    public boolean supports(String modelName, ChatResponse chatResponse) {
        return StringUtils.containsIgnoreCase(modelName, MODEL_CLAUDE)
                || StringUtils.containsIgnoreCase(modelName, MODEL_ANTHROPIC);
    }

    @Override
    public AiCodingModelStreamParser createParser() {
        return new ClaudeModelStreamParser();
    }

    private final class ClaudeModelStreamParser implements AiCodingModelStreamParser {

        private final TaggedThinkingSplitter splitter = new TaggedThinkingSplitter();
        private boolean independentReasoningSeen;

        @Override
        public AiCodingModelStreamDelta parse(ChatResponse chatResponse) {
            AiCodingModelStreamDelta delta = ClaudeAiCodingModelStreamAdapter.super.parse(chatResponse);
            String independentReasoning = AiCodingReasoningContentExtractor.extract(delta.getAssistantMessage());
            if (StringUtils.isNotBlank(independentReasoning)) {
                independentReasoningSeen = true;
            }
            delta.setTextContent(splitter.accept(delta.getTextContent()))
                    .setReasoningContent(independentReasoning);
            return delta;
        }

        @Override
        public AiCodingModelStreamDelta finish() {
            AiCodingModelStreamDelta delta = new AiCodingModelStreamDelta()
                    .setTextContent(splitter.finishText());
            if (!independentReasoningSeen) {
                delta.setReasoningContent(splitter.fallbackReasoning());
            }
            return delta;
        }
    }

    /**
     * 只识别 Claude fallback thinking 的两个固定标签，并保留跨 chunk 的最长可能标签前缀。
     */
    private static final class TaggedThinkingSplitter {

        private final StringBuilder pending = new StringBuilder();
        private final StringBuilder fallbackReasoning = new StringBuilder();
        private boolean insideThinking;

        String accept(String chunk) {
            if (StringUtils.isEmpty(chunk) && pending.length() == 0) {
                return StringUtils.EMPTY;
            }
            String remaining = pending.append(StringUtils.defaultString(chunk)).toString();
            pending.setLength(0);
            StringBuilder visibleText = new StringBuilder();
            while (StringUtils.isNotEmpty(remaining)) {
                String expectedTag = insideThinking ? CLOSE_THINK_TAG : OPEN_THINK_TAG;
                int tagIndex = remaining.indexOf(expectedTag);
                if (tagIndex >= 0) {
                    appendContent(remaining.substring(0, tagIndex), visibleText);
                    insideThinking = !insideThinking;
                    remaining = remaining.substring(tagIndex + expectedTag.length());
                    continue;
                }
                int retainedLength = longestTagPrefixSuffix(remaining, expectedTag);
                appendContent(remaining.substring(0, remaining.length() - retainedLength), visibleText);
                if (retainedLength > 0) {
                    pending.append(remaining.substring(remaining.length() - retainedLength));
                }
                break;
            }
            return visibleText.toString();
        }

        String finishText() {
            if (pending.length() == 0) {
                return StringUtils.EMPTY;
            }
            String remaining = pending.toString();
            pending.setLength(0);
            if (insideThinking) {
                fallbackReasoning.append(remaining);
                return StringUtils.EMPTY;
            }
            return remaining;
        }

        String fallbackReasoning() {
            return fallbackReasoning.toString();
        }

        private void appendContent(String content, StringBuilder visibleText) {
            if (StringUtils.isEmpty(content)) {
                return;
            }
            if (insideThinking) {
                fallbackReasoning.append(content);
            } else {
                visibleText.append(content);
            }
        }

        private int longestTagPrefixSuffix(String value, String expectedTag) {
            int maxLength = Math.min(value.length(), expectedTag.length() - 1);
            for (int length = maxLength; length > 0; length--) {
                if (value.regionMatches(value.length() - length, expectedTag, 0, length)) {
                    return length;
                }
            }
            return 0;
        }
    }
}
