package dev.a2flow.management.aicoding.tool.skill;

import lombok.Data;
import lombok.Builder;
import lombok.extern.jackson.Jacksonized;

/** JSON request for the Runtime query port; no company RPC dependency. */
@Data
@Builder(builderClassName = "Builder", builderMethodName = "newBuilder", setterPrefix = "set")
@Jacksonized
public class QueryLabTraceDetailRequest {
    @lombok.Builder.Default private String messageId = "";
    private long agentId;
}
