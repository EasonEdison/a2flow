package dev.a2flow.management.event;

import lombok.EqualsAndHashCode;
import lombok.Getter;

/**
 * AI Coding 可见思考摘要内容块。
 *
 * <p>该 block 只承载可以展示给 M 端用户的阶段摘要，例如“我已确认当前工作区为空，准备读取目录”。
 * 它不是模型隐藏思维链，不记录系统提示词、完整推理过程、工具内部实现或敏感信息。下游只应放在
 * ExecutionTraceLayer 中展示。
 */
@Getter
@EqualsAndHashCode(callSuper = true)
public final class AiCodingThinkingBlock extends AiCodingModelContentBlock {

    private final String text;

    public AiCodingThinkingBlock(String text) {
        super(TYPE_THINKING);
        this.text = text;
    }
}
