package dev.a2flow.management.aicoding.engine;

import org.springframework.ai.chat.model.ChatResponse;

/**
 * SkillFactory AI Coding 模型流协议适配器。
 *
 * <p>该接口隔离 DeepSeek、Qwen、GLM、Claude 等不同厂商的流式协议差异。差异不仅包括
 * thinking/reasoning 字段，还包括正文 delta、tool call 增量、usage 统计、finish reason
 * 和厂商 metadata 的位置。`AiCodingReActEngine` 只依赖该接口返回的统一增量，不直接解析某个
 * 厂商的原始字段，从而保证模型切换时只新增适配器而不改 AI Coding 主流程。
 */
public interface AiCodingModelStreamAdapter {

    /**
     * 判断当前适配器是否支持本次模型流响应。
     *
     * @param modelName 当前 KConf 配置的模型名
     * @param chatResponse 原始 Spring AI 流式响应
     * @return true 表示由该适配器解析
     */
    boolean supports(String modelName, ChatResponse chatResponse);

    /**
     * 将厂商原始流式响应解析成 AI Coding 内部统一增量。
     */
    AiCodingModelStreamDelta parse(ChatResponse chatResponse);

    /**
     * 为一次模型流创建独立解析器。无跨 chunk 状态的适配器继续复用当前 `parse` 实现。
     */
    default AiCodingModelStreamParser createParser() {
        return this::parse;
    }
}
