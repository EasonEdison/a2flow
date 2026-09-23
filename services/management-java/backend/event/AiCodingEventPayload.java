package dev.a2flow.management.event;

import java.util.List;
import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory AI Coding 结构化事件 payload。
 *
 * <p>该对象是 AI Coding runtime payload 的标准 JSON 结构。上游由 AI Coding 文件服务、
 * 文件变更服务和 observation 服务填充，下游通过 AgentStreamEvent 的 `payloadType/payloadJson`
 * 透传。旧 `content` JSON 只作为兼容期降级展示，不再作为主渲染协议。
 */
@Data
@Accessors(chain = true)
public class AiCodingEventPayload {

    public static final String SCHEMA_VERSION = "skill-factory.ai-coding-event/v1";

    /**
     * 协议版本。
     */
    private String schemaVersion;

    /**
     * 标准业务事件码。
     */
    private String eventCode;

    /**
     * 兼容旧前端的事件字段，值与 eventCode 保持一致。
     */
    private String eventType;

    /**
     * 事件分类。
     */
    private String category;

    /**
     * 前端展示标题。
     */
    private String title;

    private String workspaceId;
    private String sessionId;
    private String messageId;
    private String runId;
    private String threadId;
    private String conversationId;
    private String surfaceId;
    private String patchId;

    private String observationId;
    private String traceId;
    private Long timestamp;
    private Boolean success;
    private String errorMsg;
    private Map<String, Object> content;

    private ObservationInfo observation;

    /**
     * Observation 摘要。
     */
    @Data
    @Accessors(chain = true)
    public static class ObservationInfo {
        private String observationId;
        private String observationType;
        private String source;
        private String summary;
        private Boolean visibleToModel;
        private Map<String, Object> stateDelta;
    }
}
