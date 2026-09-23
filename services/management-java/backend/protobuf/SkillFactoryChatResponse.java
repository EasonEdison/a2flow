package dev.a2flow.management.protobuf;

import lombok.Data;
import lombok.Builder;
import lombok.extern.jackson.Jacksonized;

/** Local JSON transport DTO. No company RPC or protobuf runtime dependency. */
@Data
@Builder(builderClassName = "Builder", builderMethodName = "newBuilder", setterPrefix = "set", toBuilder = true)
@Jacksonized
public class SkillFactoryChatResponse {
    @lombok.Builder.Default private String schemaVersion = "";
    @lombok.Builder.Default private String eventType = "";
    @lombok.Builder.Default private String eventId = "";
    @lombok.Builder.Default private String blockId = "";
    @lombok.Builder.Default private String source = "";
    @lombok.Builder.Default private String messageId = "";
    @lombok.Builder.Default private String runId = "";
    @lombok.Builder.Default private String threadId = "";
    @lombok.Builder.Default private String conversationId = "";
    @lombok.Builder.Default private String traceId = "";
    @lombok.Builder.Default private String modelContentBlockJson = "";
    @lombok.Builder.Default private String payloadType = "";
    @lombok.Builder.Default private String payloadJson = "";
    @lombok.Builder.Default private String content = "";
    @lombok.Builder.Default private String toolCallId = "";
    @lombok.Builder.Default private String toolName = "";
    @lombok.Builder.Default private String toolArgs = "";
    @lombok.Builder.Default private String invokeId = "";
    private long tokenCount;
    private long enterTokenCount;
    private long outputTokenCount;
    private long timestamp;
    private long answerAgentId;
    private boolean toolSuccess;
    private boolean hasKnowledge;
    public boolean getToolSuccess() { return toolSuccess; }
    public boolean getHasKnowledge() { return hasKnowledge; }
}
