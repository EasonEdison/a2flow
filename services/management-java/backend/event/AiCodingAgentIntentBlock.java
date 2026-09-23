package dev.a2flow.management.event;

import java.util.Map;

import lombok.EqualsAndHashCode;
import lombok.Getter;

/**
 * AI Coding 受控业务意图内容块。
 *
 * <p>该 block 预留给模型通过白名单工具或 schema 选择 `agentUiDsl + params` 这类业务意图。
 * 它不允许模型自由手写完整 A2UI JSON；后续仍由 SkillFactory runtime 校验后再转换成业务交互
 * 或运行态渲染 payload。
 */
@Getter
@EqualsAndHashCode(callSuper = true)
public final class AiCodingAgentIntentBlock extends AiCodingModelContentBlock {

    private final String agentUiDsl;
    private final Map<String, Object> params;

    public AiCodingAgentIntentBlock(String agentUiDsl, Map<String, Object> params) {
        super(TYPE_AGENT_INTENT);
        this.agentUiDsl = agentUiDsl;
        this.params = params;
    }
}
