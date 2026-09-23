package dev.a2flow.management.event;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * AI Coding 运行态 payload 的传输属性。
 *
 * <p>该对象只描述 runtime 事件的 payload 类型、JSON 内容、工具字段和 token 用量，
 * 由 `AiCodingRuntimePayloadEvent` 聚合。模型内容不得放入该对象。
 */
@Data
@Accessors(chain = true)
public class AiCodingRuntimePayload {

    private String payloadType;
    private String payloadJson;
    private String toolCallId;
    private String toolName;
    private String toolArgs;
    private boolean toolSuccess;
    private int tokenCount;
    private int enterTokenCount;
    private int outputTokenCount;
    private boolean hasKnowledge;
}
