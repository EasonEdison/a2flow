package dev.a2flow.management.event;

import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;

/**
 * SkillFactory AI Coding 事件 JSON 编解码边界。
 *
 * <p>所有写入 `AgentStreamEvent.payloadJson` 的 AI Coding 结构化 JSON 都必须从该类输出，
 * 禁止在 Engine、Tool 或前端协议适配里手写 JSON 字符串，保证字段命名、兼容字段和协议版本统一。
 * 旧 `content` 字段只允许放摘要或兼容期降级展示。
 */
@Component
public class AiCodingEventPayloadCodec {

    /**
     * 将标准 payload 序列化为 JSON 字符串。
     */
    public String toJson(AiCodingEventPayload payload) {
        return JsonSupport.toJSON(payload);
    }
}
