package dev.a2flow.management.host;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.a2flow.management.access.ManagementIdentityProvider;
import dev.a2flow.management.entry.ManualManagementExecuteService;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.context.support.WebApplicationContextUtils;

/** 只提供原工作台的手填方法入口；SSE结束不代表任何业务运行完成。 */
public final class ManagementHttpServlet extends HttpServlet {
    private static final Set<String> IDENTITY_FIELDS = Set.of("userId", "userName", "operator", "role", "roles");

    @Override
    protected void doPost(HttpServletRequest request, HttpServletResponse response) throws IOException {
        var context = WebApplicationContextUtils.getRequiredWebApplicationContext(getServletContext());
        ObjectMapper mapper = context.getBean(ObjectMapper.class);
        String traceId = UUID.randomUUID().toString();
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("X-Content-Type-Options", "nosniff");
        response.setCharacterEncoding("UTF-8");
        try {
            new ManagementHttpPolicy(context.getEnvironment()).check(request);
            context.getBean(ManagementIdentityProvider.class).userId();
            String path = request.getRequestURI();
            if (path.equals("/api/management/v2/chat")) {
                writeError(response, mapper, 409, "AI_ASSISTANCE_DISABLED", traceId);
                return;
            }
            if (!path.equals("/api/management/v2/handler") && !path.equals("/api/management/v2/bizrender")) {
                writeError(response, mapper, 404, "MANAGEMENT_ROUTE_NOT_SUPPORTED", traceId);
                return;
            }
            if (request.getContentType() == null || !request.getContentType().split(";", 2)[0].trim().equalsIgnoreCase("application/json")) {
                writeError(response, mapper, 415, "JSON_REQUIRED", traceId);
                return;
            }
            JsonNode body = mapper.readTree(ManagementHttpPolicy.readBody(request));
            if (body == null || !body.isObject() || !body.path("method").isTextual()) {
                throw new IllegalArgumentException("METHOD_REQUIRED");
            }
            JsonNode params = body.path("params");
            if (!params.isMissingNode() && !params.isObject()) throw new IllegalArgumentException("PARAMS_OBJECT_REQUIRED");
            Map<String, String> values = new LinkedHashMap<>();
            var fields = params.fields();
            while (fields.hasNext()) {
                var field = fields.next();
                if (IDENTITY_FIELDS.contains(field.getKey())) throw new SecurityException("CLIENT_IDENTITY_FIELDS_NOT_ALLOWED");
                JsonNode value = field.getValue();
                if (!value.isNull()) values.put(field.getKey(), value.isValueNode() ? value.asText() : mapper.writeValueAsString(value));
            }
            var transaction = new TransactionTemplate(context.getBean(PlatformTransactionManager.class));
            var result = transaction.execute(status -> {
                var reply = context.getBean(ManualManagementExecuteService.class).execute(body.path("method").textValue(), values, traceId);
                if (!reply.isSuccess()) status.setRollbackOnly();
                return reply;
            });
            if (result == null) throw new IllegalStateException("EMPTY_MANAGEMENT_RESULT");
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("result", result.isSuccess() ? 1 : 0);
            envelope.put("data", result.getData());
            envelope.put("isList", result.isList());
            envelope.put("errorMsg", result.getErrorMsg());
            envelope.put("traceId", traceId);
            String json = mapper.writeValueAsString(envelope);
            if (path.endsWith("/handler")) {
                response.setContentType("text/event-stream;charset=UTF-8");
                response.getWriter().write("data: " + json + "\n\ndata: [DONE]\n\n");
            } else {
                response.setContentType("application/json;charset=UTF-8");
                response.getWriter().write(json);
            }
        } catch (SecurityException failure) {
            writeError(response, mapper, failure.getMessage().contains("AUTHENTICATION") ? 401 : 403, failure.getMessage(), traceId);
        } catch (IllegalArgumentException | com.fasterxml.jackson.core.JsonProcessingException failure) {
            writeError(response, mapper, 400, "INVALID_MANAGEMENT_REQUEST", traceId);
        } catch (RuntimeException failure) {
            // Spring wraps request-scoped construction failures; do not expose SQL, cookies or stack traces to clients.
            Throwable cause = failure;
            while (cause.getCause() != null && cause.getCause() != cause) cause = cause.getCause();
            if (cause instanceof SecurityException) {
                writeError(response, mapper, 401, "ACCOUNT_AUTHENTICATION_REQUIRED", traceId);
            } else {
                org.slf4j.LoggerFactory.getLogger(getClass()).error("Management request failed traceId={} type={}", traceId, failure.getClass().getSimpleName());
                writeError(response, mapper, 500, "MANAGEMENT_REQUEST_FAILED", traceId);
            }
        }
    }

    private static void writeError(HttpServletResponse response, ObjectMapper mapper, int status, String code, String traceId) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json;charset=UTF-8");
        mapper.writeValue(response.getWriter(), Map.of("result", 0, "errorMsg", code, "traceId", traceId));
    }
}
