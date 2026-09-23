package dev.a2flow.management.protobuf;

import lombok.Data;
import lombok.Builder;
import lombok.extern.jackson.Jacksonized;

/** Local JSON transport DTO. No company RPC or protobuf runtime dependency. */
@Data
@Builder(builderClassName = "Builder", builderMethodName = "newBuilder", setterPrefix = "set", toBuilder = true)
@Jacksonized
public class InvokeRequest {
    @lombok.Builder.Default private String bizKey = "";
    @lombok.Builder.Default private String ownerId = "";
    @com.fasterxml.jackson.databind.annotation.JsonDeserialize(using = dev.a2flow.management.access.UserIdWireDeserializer.class)
    @lombok.Builder.Default private String userId = "";
    @lombok.Builder.Default private String sessionId = "";
    @lombok.Builder.Default private String message = "";
    @lombok.Builder.Default private String invokeId = "";
    private long agentId;
    private boolean createSession;
    @lombok.Builder.Default private java.util.Map<String, String> bizContext = new java.util.LinkedHashMap<>();
    @lombok.Builder.Default private java.util.Map<Long, RecallKnowledgeParam> recallKnowledgeParam = new java.util.LinkedHashMap<>();
    public boolean getCreateSession() { return createSession; }
    @com.fasterxml.jackson.annotation.JsonIgnore
    public java.util.Map<String, String> getBizContextMap() { return bizContext; }
    @com.fasterxml.jackson.annotation.JsonIgnore
    public java.util.Map<Long, RecallKnowledgeParam> getRecallKnowledgeParamMap() { return recallKnowledgeParam; }
    public static class Builder {
        public Builder clearBizContext() { return setBizContext(new java.util.LinkedHashMap<>()); }
        public Builder putAllBizContext(java.util.Map<String,String> values) {
            return setBizContext(new java.util.LinkedHashMap<>(values));
        }
    }
}
