package dev.a2flow.management.managementagent;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.protobuf.ByteString;
import io.grpc.stub.StreamObserver;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import dev.a2flow.management.lifecycle.SkillFactoryMethodDispatcher;
import dev.a2flow.management.managementagent.proto.*;

/** Trusted callback surface, explicit tool allowlist, normal domain guards and durable mutation receipts. */
public final class ManagementToolsService extends ManagementToolsGrpc.ManagementToolsImplBase {
    private final ManagementAgentGrantStore grants;
    private final ManagementToolCatalog catalog;
    private final ManagementAuthoringContracts contracts;
    private final ManagementCapabilityGuard capabilityGuard;
    private final ManagementToolReceiptStore receipts;
    private final SkillFactoryMethodDispatcher dispatcher;
    private final ObjectMapper mapper;
    private final TransactionTemplate transaction;
    private final Set<String> active = ConcurrentHashMap.newKeySet();

    public ManagementToolsService(ManagementAgentGrantStore grants, ManagementToolCatalog catalog,
            ManagementToolReceiptStore receipts, SkillFactoryMethodDispatcher dispatcher,
            ObjectMapper mapper, PlatformTransactionManager transactions, ManagementAuthoringContracts contracts, ManagementCapabilityGuard capabilityGuard) {
        this.capabilityGuard = capabilityGuard; this.contracts = contracts; this.grants = grants; this.catalog = catalog; this.receipts = receipts;
        this.dispatcher = dispatcher; this.mapper = mapper; this.transaction = new TransactionTemplate(transactions);
    }
    @Override public void describeTools(DescribeToolsRequest request, StreamObserver<DescribeToolsResponse> observer) {
        try {
            grants.resolve(request.getGrant());
            observer.onNext(DescribeToolsResponse.newBuilder().addAllTools(catalog.tools()).build());
        } catch (SecurityException error) {
            observer.onNext(DescribeToolsResponse.newBuilder().setErrorCode(error.getMessage()).build());
        }
        observer.onCompleted();
    }
    @Override public void executeTool(ExecuteToolRequest request, StreamObserver<ToolResult> observer) {
        ToolResult result;
        try { result = execute(request); }
        catch (com.fasterxml.jackson.core.JsonProcessingException error) { result = result(request.getRequestId(), "REJECTED", "MANAGEMENT_TOOL_ARGUMENTS_INVALID"); }
        catch (SecurityException | IllegalArgumentException error) { result = result(request.getRequestId(), "REJECTED", safeCode(error.getMessage(), "MANAGEMENT_TOOL_ARGUMENTS_INVALID")); }
        catch (Exception error) {
            org.slf4j.LoggerFactory.getLogger(getClass()).error("Management tool boundary failure type={}", error.getClass().getSimpleName());
            result = result(request.getRequestId(), "UNKNOWN", "MANAGEMENT_TOOL_RESULT_UNKNOWN");
        }
        observer.onNext(result); observer.onCompleted();
    }
    @Override public void readReceipt(ReadReceiptRequest request, StreamObserver<ToolResult> observer) {
        ToolResult result;
        try {
            var grant = grants.resolve(request.getGrant());
            grant.requireConversation(request.getConversationId());
            requireId(request.getRequestId());
            var receipt = receipts.read(grant, request.getRequestId());
            result = receipt == null ? result(request.getRequestId(), "NOT_FOUND", "") : visible(grant, receipt.result());
        } catch (SecurityException | IllegalArgumentException error) {
            // A failed lookup says nothing about the original operation's outcome.
            result = result(request.getRequestId(), "UNKNOWN", safeCode(error.getMessage(), "MANAGEMENT_TOOL_ARGUMENTS_INVALID"));
        } catch (Exception error) { result = result(request.getRequestId(), "UNKNOWN", "MANAGEMENT_TOOL_RECEIPT_UNAVAILABLE"); }
        observer.onNext(result); observer.onCompleted();
    }
    private ToolResult execute(ExecuteToolRequest request) throws Exception {
        var grant = grants.resolve(request.getGrant());
        grant.requireConversation(request.getConversationId());
        requireId(request.getRequestId()); requireId(request.getTurnId()); requireId(request.getToolCallId());
        if (request.getArgumentsJson().size() > 1024 * 1024) throw new IllegalArgumentException("MANAGEMENT_TOOL_ARGUMENTS_TOO_LARGE");
        JsonNode arguments = mapper.readTree(request.getArgumentsJson().toByteArray());
        checkDepth(arguments, 0);
        var definition = catalog.require(request.getName(), arguments);
        String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(
                mapper.writeValueAsBytes(Map.of("method", request.getName(), "arguments", canonical(arguments)))));
        if (!definition.mutating()) {
            try (var operation = new ManagementOperationContext(grant)) { return dispatch(request, grant, arguments); }
        }
        String key = activeKey(grant, request.getRequestId());
        if (!receipts.claim(grant, request, digest)) {
            var previous = receipts.read(grant, request.getRequestId());
            if (previous == null) return result(request.getRequestId(), "UNKNOWN", "MANAGEMENT_TOOL_RECEIPT_UNAVAILABLE");
            if (!previous.digest().equals(digest)) return result(request.getRequestId(), "REJECTED", "MANAGEMENT_TOOL_REQUEST_CONFLICT");
            return visible(grant, previous.result());
        }
        active.add(key);
        try (var operation = new ManagementOperationContext(grant)) {
            var completed = new java.util.concurrent.atomic.AtomicBoolean();
            ToolResult response = transaction.execute(status -> {
                ToolResult reply;
                try {
                    JsonNode effectiveArguments = switch (request.getName()) {
                        case "CAPABILITY_DRAFT_CREATE_FROM_REGISTERED" -> capabilityGuard.registeredCreateArguments(arguments);
                        case "CAPABILITY_DRAFT_UPDATE_METADATA" -> capabilityGuard.metadataUpdateArguments(arguments);
                        default -> arguments;
                    };
                    capabilityGuard.check(dispatchMethod(request.getName()), effectiveArguments);
                    reply = dispatch(request, grant, effectiveArguments);
                } catch (IllegalArgumentException rejection) {
                    reply = result(request.getRequestId(), "REJECTED", safeCode(rejection.getMessage(), "MANAGEMENT_CAPABILITY_CONTRACT_INVALID"));
                }
                if (!domainOperationSucceeded(reply)) status.setRollbackOnly();
                else { receipts.complete(grant, reply); completed.set(true); }
                return reply;
            });
            if (response == null) throw new IllegalStateException("Empty management tool result");
            if (!completed.get()) receipts.complete(grant, response);
            return response;
        } catch (Exception error) {
            // A runtime publication can commit separately from the management transaction. Never replay uncertainty.
            ToolResult unknown = result(request.getRequestId(), "UNKNOWN", "MANAGEMENT_TOOL_RESULT_UNKNOWN");
            try { receipts.complete(grant, unknown); } catch (RuntimeException ignored) { /* CLAIMED remains UNKNOWN on restart. */ }
            org.slf4j.LoggerFactory.getLogger(getClass()).error("Management tool execution uncertain method={} type={}", request.getName(), error.getClass().getSimpleName());
            return unknown;
        } finally { active.remove(key); }
    }
    private ToolResult dispatch(ExecuteToolRequest request, ManagementAgentGrantStore.Grant grant, JsonNode arguments) {
        try {
            Map<String, String> params = new LinkedHashMap<>();
            arguments.fields().forEachRemaining(field -> params.put(field.getKey(), field.getValue().isValueNode()
                    ? field.getValue().asText() : field.getValue().toString()));
            String user = Long.toString(grant.userId());
            params.put("userId", user); params.put("userName", user); params.put("operator", user);
            params.put("environment", "PRT"); params.put("requestId", request.getRequestId());
            var reply = request.getName().equals("AUTHORING_CONTRACT")
                    ? dev.a2flow.management.model.SkillFactoryExecutionResult.success(contracts.describe(), false)
                    : dispatcher.execute(user, dispatchMethod(request.getName()), params);
            JsonNode data = mapper.valueToTree(reply.getData());
            boolean dryRun = request.getName().equals("CAPABILITY_DRY_RUN_READ_ONLY");
            boolean dryRunPassed = data.path("toolResult").path("success").asBoolean(false);
            if (reply.isSuccess() && dryRun) data = dryRunSummary(data, params, dryRunPassed);
            String code = reply.isSuccess() ? "" : safeCode(data.path("errorCode").asText(), "MANAGEMENT_TOOL_VALIDATION_REJECTED");
            String outcome = reply.isSuccess() ? "SUCCEEDED" : code.equals("INTERNAL_SERVER_ERROR") ? "UNKNOWN" : "REJECTED";
            if (reply.isSuccess() && dryRun && !dryRunPassed) {
                outcome = "REJECTED"; code = "MANAGEMENT_CAPABILITY_DRY_RUN_FAILED";
            }
            if (reply.isSuccess() && (request.getName().equals("CAPABILITY_VALIDATE") || request.getName().equals("RUNTIME_VALIDATE"))
                    && data.has("valid") && !data.path("valid").asBoolean()) {
                outcome = "REJECTED"; code = "MANAGEMENT_ASSET_VALIDATION_FAILED";
            }
            if (reply.isSuccess() && request.getName().equals("RELEASE_PREPROD_DEPLOY") && !data.path("status").asText().equals("SUCCEEDED")) {
                String state = data.path("status").asText();
                outcome = Set.of("FAILED", "PARTIAL_FAILED", "PLATFORM_PENDING").contains(state) ? "REJECTED" : "UNKNOWN";
                code = outcome.equals("UNKNOWN") ? "MANAGEMENT_PUBLICATION_RESULT_UNKNOWN" : "MANAGEMENT_PUBLICATION_REJECTED";
            }
            var body = mapper.createObjectNode().put("success", reply.isSuccess()).put("isList", reply.isList());
            body.set("data", data);
            body.set("assets", reply.isSuccess() ? ManagementAssetProjection.assets(mapper, request.getName(), params, data) : mapper.createArrayNode());
            body.put("errorMsg", reply.getErrorMsg() == null ? "" : reply.getErrorMsg());
            return ToolResult.newBuilder().setRequestId(request.getRequestId()).setStatus(outcome)
                    .setErrorCode(code).setResultJson(ByteString.copyFromUtf8(body.toString())).build();
        } catch (Exception error) { throw new IllegalStateException("MANAGEMENT_TOOL_DISPATCH_FAILED", error); }
    }
    private JsonNode dryRunSummary(JsonNode data, Map<String, String> params, boolean passed) {
        // The existing service persists real evidence. Do not retain its transient request or business response.
        var summary = mapper.createObjectNode().put("draftId", params.get("draftId"))
                .put("revision", params.get("revision")).put("environment", "PRT")
                .put("clientType", params.get("clientType")).put("verificationStatus", passed ? "PASSED" : "FAILED");
        var result = summary.putObject("toolResult").put("success", passed);
        JsonNode source = data.path("toolResult");
        String code = safeCode(source.path("errorCode").asText(), "");
        if (!code.isEmpty()) result.put("errorCode", code);
        if (source.path("httpStatus").isIntegralNumber()) result.set("httpStatus", source.path("httpStatus"));
        return summary;
    }
    private static String dispatchMethod(String toolName) {
        return switch (toolName) {
            case "CAPABILITY_DRAFT_CREATE_FROM_REGISTERED" -> "CAPABILITY_DRAFT_CREATE";
            case "CAPABILITY_DRAFT_UPDATE_METADATA" -> "CAPABILITY_DRAFT_SAVE";
            case "CAPABILITY_DRY_RUN_READ_ONLY" -> "CAPABILITY_DRY_RUN";
            default -> toolName;
        };
    }
    private boolean domainOperationSucceeded(ToolResult result) {
        try { return mapper.readTree(result.getResultJson().toByteArray()).path("success").asBoolean(false); }
        catch (java.io.IOException error) { throw new IllegalStateException("Invalid internal tool result", error); }
    }
    private ToolResult visible(ManagementAgentGrantStore.Grant grant, ToolResult receipt) {
        if (!receipt.getStatus().equals("CLAIMED")) return receipt;
        boolean running = active.contains(activeKey(grant, receipt.getRequestId()));
        return receipt.toBuilder().setStatus(running ? "RUNNING" : "UNKNOWN")
                .setErrorCode(running ? "MANAGEMENT_TOOL_IN_PROGRESS" : "MANAGEMENT_TOOL_RESULT_UNKNOWN").build();
    }
    private static String activeKey(ManagementAgentGrantStore.Grant grant, String requestId) {
        return grant.namespace() + ":" + grant.userId() + ":" + grant.conversationId() + ":" + requestId;
    }
    public static void requireId(String value) {
        if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}")) throw new IllegalArgumentException("MANAGEMENT_TOOL_IDENTIFIER_INVALID");
    }
    private static String safeCode(String value, String fallback) { return value != null && value.matches("[A-Z][A-Z0-9_]{0,159}") ? value : fallback; }
    private static ToolResult result(String requestId, String status, String code) {
        return ToolResult.newBuilder().setRequestId(requestId).setStatus(status).setErrorCode(code).setResultJson(ByteString.copyFromUtf8("{}")).build();
    }
    private static void checkDepth(JsonNode value, int depth) {
        if (depth > 32) throw new IllegalArgumentException("MANAGEMENT_TOOL_ARGUMENTS_TOO_DEEP");
        if (value != null && value.isContainerNode()) value.forEach(child -> checkDepth(child, depth + 1));
    }
    private Object canonical(JsonNode value) {
        if (value.isObject()) { Map<String, Object> result = new TreeMap<>(); value.fields().forEachRemaining(field -> result.put(field.getKey(), canonical(field.getValue()))); return result; }
        if (value.isArray()) { var result = new ArrayList<>(); value.forEach(child -> result.add(canonical(child))); return result; }
        return value;
    }
}
