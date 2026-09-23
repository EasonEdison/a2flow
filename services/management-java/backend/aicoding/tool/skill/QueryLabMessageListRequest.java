package dev.a2flow.management.aicoding.tool.skill;

import lombok.Data;
import lombok.Builder;
import lombok.extern.jackson.Jacksonized;

/** JSON request for the Runtime query port; no company RPC dependency. */
@Data
@Builder(builderClassName = "Builder", builderMethodName = "newBuilder", setterPrefix = "set")
@Jacksonized
public class QueryLabMessageListRequest {
    @lombok.Builder.Default private String userId = "";
    @lombok.Builder.Default private String conversationId = "";
    @lombok.Builder.Default private String messageId = "";
    @lombok.Builder.Default private String bizIdentifyId = "";
    @lombok.Builder.Default private String skillCode = "";
    @lombok.Builder.Default private String skillKeyword = "";
    @lombok.Builder.Default private String runStatus = "";
    @lombok.Builder.Default private String sortField = "";
    @lombok.Builder.Default private String sortOrder = "";
    private long startTime;
    private long endTime;
    private long sellerId;
    private long agentId;
    private int page;
    private int pageSize;
}
