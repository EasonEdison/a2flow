package dev.a2flow.management.managementagent;

import java.io.IOException;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.a2flow.management.access.ManagementIdentityProvider;
import dev.a2flow.management.host.ManagementHttpPolicy;
import dev.a2flow.management.managementagent.proto.*;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.context.support.WebApplicationContextUtils;

/** Authenticated global management Chat boundary; legacy /chat remains disabled. */
public final class ManagementAgentServlet extends HttpServlet {
    private static final String PREFIX = "/api/management/v2/agent/conversations/";
    private static final Map<String, Set<String>> FIELDS = Map.of(
            "create", Set.of("requestId", "title"), "list", Set.of("pageToken", "limit"),
            "read", Set.of("conversationId", "afterEventSeq", "limit"),
            "send", Set.of("conversationId", "requestId", "message"));
    @Override protected void doPost(HttpServletRequest request, HttpServletResponse response) throws IOException {
        var application = WebApplicationContextUtils.getRequiredWebApplicationContext(getServletContext());
        ObjectMapper mapper = application.getBean(ObjectMapper.class);
        String traceId = UUID.randomUUID().toString();
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("X-Content-Type-Options", "nosniff");
        response.setCharacterEncoding("UTF-8");
        response.setContentType("application/json;charset=UTF-8");
        try {
            new ManagementHttpPolicy(application.getEnvironment()).check(request);
            var identity = application.getBean(ManagementIdentityProvider.class);
            identity.userId();
            if (!identity.isAdministrator()) throw new SecurityException("ADMIN_REQUIRED");
            String path = request.getRequestURI();
            String action = path.startsWith(PREFIX) ? path.substring(PREFIX.length()) : "";
            if (!FIELDS.containsKey(action)) { error(response, mapper, 404, "MANAGEMENT_AGENT_ROUTE_NOT_FOUND", traceId); return; }
            if (request.getContentType() == null || !request.getContentType().split(";", 2)[0].trim().equalsIgnoreCase("application/json")) {
                error(response, mapper, 415, "JSON_REQUIRED", traceId); return;
            }
            JsonNode input = mapper.readTree(ManagementHttpPolicy.readBody(request));
            if (input == null || !input.isObject()) throw new IllegalArgumentException("Object required");
            input.fieldNames().forEachRemaining(field -> { if (!FIELDS.get(action).contains(field)) throw new IllegalArgumentException("Unknown field"); });
            var context = AgentContext.newBuilder().setUserId(identity.userId()).setNamespace(identity.namespace()).setEnvironment("PRT");
            String conversationId = action.equals("read") || action.equals("send") ? identifier(input, "conversationId", 128) : "";
            String requestId = action.equals("create") || action.equals("send") ? identifier(input, "requestId", 160) : "read:" + conversationId;
            if (action.equals("read") || action.equals("send")) context.setGrant(application.getBean(ManagementAgentGrantStore.class).issue(identity, conversationId, requestId));
            var client = application.getBean(ManagementAgentClient.class).stub();
            ObjectNode data = mapper.createObjectNode();
            String code;
            switch (action) {
                case "create" -> {
                    var reply = client.createConversation(CreateConversationRequest.newBuilder().setContext(context).setRequestId(requestId)
                            .setTitle(text(input, "title", 256, false)).build());
                    code = reply.getErrorCode(); data.set("conversation", conversation(mapper, reply.getConversation()));
                }
                case "list" -> {
                    var reply = client.listConversations(ListConversationsRequest.newBuilder().setContext(context)
                            .setPageToken(text(input, "pageToken", 512, false)).setLimit(integer(input, "limit", 30, 1, 100)).build());
                    code = reply.getErrorCode(); var items = data.putArray("items");
                    reply.getItemsList().forEach(value -> items.add(conversation(mapper, value)));
                    data.put("nextPageToken", reply.getNextPageToken());
                }
                case "read" -> {
                    long after = input.has("afterEventSeq") ? input.path("afterEventSeq").longValue() : 0;
                    if (input.has("afterEventSeq") && (!input.path("afterEventSeq").isIntegralNumber() || !input.path("afterEventSeq").canConvertToLong() || after < 0)) throw new IllegalArgumentException("Invalid cursor");
                    var reply = client.readConversation(ReadConversationRequest.newBuilder().setContext(context).setConversationId(conversationId)
                            .setAfterEventSeq(after).setLimit(integer(input, "limit", 100, 1, 200)).build());
                    code = reply.getErrorCode(); data.set("conversation", conversation(mapper, reply.getConversation()));
                    var turns = data.putArray("turns");
                    reply.getTurnsList().forEach(turn -> turns.addObject().put("turnId", turn.getTurnId()).put("requestId", turn.getRequestId())
                            .put("status", turn.getStatus()).put("message", turn.getMessage()).put("finalText", turn.getFinalText()).put("errorCode", turn.getErrorCode()));
                    var events = data.putArray("events");
                    for (var event : reply.getEventsList()) {
                        var value = events.addObject().put("sequence", event.getSequence()).put("turnId", event.getTurnId()).put("type", event.getType());
                        value.set("payload", event.getPayloadJson().isEmpty() ? mapper.createObjectNode() : mapper.readTree(event.getPayloadJson().toByteArray()));
                    }
                    data.put("nextEventSeq", reply.getNextEventSeq()).put("hasMore", reply.getHasMore())
                            .put("canSend", reply.getCanSend()).put("mutationsBlocked", reply.getMutationsBlocked());
                }
                case "send" -> {
                    var reply = client.sendMessage(SendMessageRequest.newBuilder().setContext(context).setConversationId(conversationId)
                            .setRequestId(requestId).setMessage(text(input, "message", 16000, true)).build());
                    code = reply.getErrorCode(); data.put("conversationId", reply.getConversationId()).put("turnId", reply.getTurnId())
                            .put("requestId", reply.getRequestId()).put("status", reply.getStatus()).put("errorCode", reply.getErrorCode());
                }
                default -> throw new IllegalArgumentException("Unknown operation");
            }
            if (!code.isEmpty()) {
                String safe = code.matches("[A-Z][A-Z0-9_]{0,159}") ? code : "MANAGEMENT_AGENT_FAILED";
                error(response, mapper, safe.endsWith("NOT_FOUND") ? 404 : 409, safe, traceId); return;
            }
            mapper.writeValue(response.getWriter(), Map.of("result", 1, "data", data, "traceId", traceId));
        } catch (SecurityException failure) {
            error(response, mapper, failure.getMessage().contains("AUTHENTICATION") ? 401 : 403, failure.getMessage(), traceId);
        } catch (IllegalArgumentException | com.fasterxml.jackson.core.JsonProcessingException failure) {
            error(response, mapper, 400, "INVALID_MANAGEMENT_AGENT_REQUEST", traceId);
        } catch (StatusRuntimeException failure) {
            boolean timeout = failure.getStatus().getCode() == Status.Code.DEADLINE_EXCEEDED;
            error(response, mapper, timeout ? 504 : 503, timeout ? "MANAGEMENT_AGENT_TIMEOUT" : "MANAGEMENT_AGENT_UNAVAILABLE", traceId);
        } catch (RuntimeException failure) {
            Throwable cause = failure;
            while (cause.getCause() != null && cause.getCause() != cause) cause = cause.getCause();
            if (cause instanceof SecurityException) error(response, mapper, 401, "ACCOUNT_AUTHENTICATION_REQUIRED", traceId);
            else {
                org.slf4j.LoggerFactory.getLogger(getClass()).error("Management Agent ingress failed traceId={} type={}", traceId, failure.getClass().getSimpleName());
                error(response, mapper, 503, "MANAGEMENT_AGENT_UNAVAILABLE", traceId);
            }
        }
    }
    private static ObjectNode conversation(ObjectMapper mapper, Conversation value) {
        return mapper.createObjectNode().put("id", value.getId()).put("title", value.getTitle()).put("createdAt", java.time.Instant.ofEpochMilli(value.getCreatedAt()).toString()).put("updatedAt", java.time.Instant.ofEpochMilli(value.getUpdatedAt()).toString());
    }
    private static String text(JsonNode input, String key, int maximum, boolean required) {
        if (!input.has(key) && !required) return "";
        JsonNode value = input.path(key);
        if (!value.isTextual() || value.textValue().length() > maximum || (required && value.textValue().isBlank())) throw new IllegalArgumentException("Invalid text");
        return value.textValue();
    }
    private static String identifier(JsonNode input, String key, int maximum) {
        String value = text(input, key, maximum, true); ManagementToolsService.requireId(value); return value;
    }
    private static int integer(JsonNode input, String key, int defaultValue, int minimum, int maximum) {
        if (!input.has(key)) return defaultValue;
        JsonNode value = input.path(key);
        if (!value.isIntegralNumber() || !value.canConvertToInt() || value.intValue() < minimum || value.intValue() > maximum) throw new IllegalArgumentException("Invalid integer");
        return value.intValue();
    }
    private static void error(HttpServletResponse response, ObjectMapper mapper, int status, String code, String traceId) throws IOException {
        response.setStatus(status);
        mapper.writeValue(response.getWriter(), Map.of("result", 0, "errorCode", code, "errorMsg", code, "traceId", traceId));
    }
}
