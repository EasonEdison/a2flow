package dev.a2flow.management.event;

import lombok.EqualsAndHashCode;
import lombok.Getter;

/**
 * AI Coding 最终正文内容块。
 *
 * <p>该 block 只用于 AnswerLayer 的 assistant 文本或 Markdown 增量，不承载工具过程、patch、
 * 审批或业务卡片。上游由 `AiCodingReActEngine` 在确认本轮没有后续工具调用后产生，下游由
 * SkillFactory 前端按 `messageId/blockId` 追加渲染。
 */
@Getter
@EqualsAndHashCode(callSuper = true)
public final class AiCodingTextBlock extends AiCodingModelContentBlock {

    private final String text;

    public AiCodingTextBlock(String text) {
        super(TYPE_TEXT);
        this.text = text;
    }
}
