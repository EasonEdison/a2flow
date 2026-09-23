package dev.a2flow.management.event;

import lombok.EqualsAndHashCode;
import lombok.Getter;

/**
 * AI Coding 模型工具调用意图内容块。
 *
 * <p>该 block 表达模型选择调用哪个工具以及参数摘要；真正的工具执行、结果、失败和 stdout/stderr
 * 由运行态 payload 事件表达。这样前端可以把“模型为什么要用工具”和“工具实际返回了什么”拆开展示。
 */
@Getter
@EqualsAndHashCode(callSuper = true)
public final class AiCodingToolUseBlock extends AiCodingModelContentBlock {

    private final String toolCallId;
    private final String toolName;
    private final Object toolArgs;

    public AiCodingToolUseBlock(String toolCallId, String toolName, Object toolArgs) {
        super(TYPE_TOOL_USE);
        this.toolCallId = toolCallId;
        this.toolName = toolName;
        this.toolArgs = toolArgs;
    }
}
