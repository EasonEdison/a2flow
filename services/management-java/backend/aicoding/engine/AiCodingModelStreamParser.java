package dev.a2flow.management.aicoding.engine;

import org.springframework.ai.chat.model.ChatResponse;

/**
 * SkillFactory 单次模型调用的有状态流解析器。
 *
 * <p>上游由一个 `AiCodingModelStreamAdapter` 为每次模型流创建独立实例，下游把归一化增量交给
 * `AiCodingReActEngine`。该生命周期允许厂商协议在 chunk 之间保留少量解析状态，例如 Claude
 * fallback thinking 标签的未完整前缀；解析器不负责 Tool 执行、事件持久化或前端展示。
 */
public interface AiCodingModelStreamParser {

    /**
     * 解析一个模型流 chunk。
     */
    AiCodingModelStreamDelta parse(ChatResponse chatResponse);

    /**
     * 模型流结束后冲刷仍在解析器中的有界内容。
     */
    default AiCodingModelStreamDelta finish() {
        return new AiCodingModelStreamDelta();
    }
}
