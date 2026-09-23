package dev.a2flow.management.agentcore.runtime.tool;


import java.math.BigDecimal;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.engine.model.BaseAgentContext;
import dev.a2flow.management.model.CapabilityActionExecutionPlan;
import dev.a2flow.management.model.CapabilityActionExecutionPreview;
import dev.a2flow.management.model.CapabilityIntegerSupport;
import dev.a2flow.management.model.CapabilityToolErrorCode;
import dev.a2flow.management.model.CapabilityToolResult;
import dev.a2flow.management.release.ReleaseEnvironment;

import lombok.extern.slf4j.Slf4j;

/**
 * 业务能力通用执行器。
 *
 * <p>只执行 GRPC 计划；复用既有参数校验和映射，传输由注册的 Protobuf unary 方法完成。
 * 模型不能覆盖身份、环境、服务目标或固定映射。运行态准入由可信引擎与已发布 A2UI 绑定负责。
 */
@Component
@Slf4j
public class CapabilityActionExecutor {

    private static final String FIELD_AGENT_CONTEXT = "agentContext";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_ITEMS = "items";
    private static final String FIELD_PROPERTIES = "properties";
    private static final String FIELD_REQUIRED = "required";
    private static final Pattern REQUEST_PATH_PATTERN = Pattern.compile(
            "^[A-Za-z0-9_-]+(?:\\.[A-Za-z0-9_-]+)*$");
    private static final Set<String> FORBIDDEN_ARGUMENTS = Set.of(
            "url", "uri", "cookie", "authorization", "headers", "header", "host", "token");

    @Resource
    private dev.a2flow.management.capabilityrpc.GrpcCapabilityTransport grpcCapabilityTransport;

    public CapabilityActionExecutor() { }

    public CapabilityActionExecutor(dev.a2flow.management.capabilityrpc.GrpcCapabilityTransport transport) {
        this.grpcCapabilityTransport = transport;
    }

    /**
     * 执行不可变业务能力计划并返回统一结构；所有预检失败都在出网前转为稳定错误码。
     */
    public String execute(CapabilityActionExecutionPlan executionPlan, String toolInput, ToolContext toolContext,
            ReleaseEnvironment requestedEnvironment, ReleaseEnvironment resolvedEnvironment) {
        return JsonSupport.toJSON(executeResult(executionPlan, toolInput, toolContext, requestedEnvironment, resolvedEnvironment));
    }

    public CapabilityToolResult executeResult(CapabilityActionExecutionPlan executionPlan, String toolInput, ToolContext toolContext,
            ReleaseEnvironment requestedEnvironment, ReleaseEnvironment resolvedEnvironment) {
        long startTime = System.currentTimeMillis();
        CapabilityToolResult result;
        try {
            PreparedExecution prepared = prepare(executionPlan, toolInput, toolContext,
                    requestedEnvironment, resolvedEnvironment);
            Object data = grpcCapabilityTransport.execute(executionPlan, prepared.preview().getEffectiveRequestBody(),
                    rpcContext(requireAgentContext(toolContext), toolContext, resolvedEnvironment));
            result = CapabilityToolResult.builder().success(true).rpcStatus("OK")
                    .actionCode(executionPlan.getActionCode()).capabilityVersion(executionPlan.getCapabilityVersion())
                    .sourceId(executionPlan.getSourceId()).sourceDigest(executionPlan.getSourceDigest())
                    .clientType(executionPlan.getClientType()).requestedEnvironment(requestedEnvironment)
                    .resolvedEnvironment(resolvedEnvironment).contentType("application/protobuf")
                    .traceId(trustedString(toolContext, TrustedToolContext.TRACE_ID)).data(data).build();
        } catch (CapabilityExecutionException exception) {
            result = failure(executionPlan, requestedEnvironment, resolvedEnvironment,
                    trustedString(toolContext, TrustedToolContext.TRACE_ID),
                    exception.getErrorCode(), exception.getMessage());
        } catch (Exception exception) {
            log.error("业务能力gRPC执行异常, actionCode={}, sourceId={}, clientType={}, "
                            + "exceptionType={}", actionCode(executionPlan), sourceId(executionPlan),
                    executionPlan == null ? StringUtils.EMPTY : executionPlan.getClientType(),
                    exception.getClass().getSimpleName());
            result = failure(executionPlan, requestedEnvironment, resolvedEnvironment,
                    trustedString(toolContext, TrustedToolContext.TRACE_ID),
                    transportError(exception),
                    "gRPC execution failed");
        }
        log.info("业务能力gRPC执行结束, actionCode={}, version={}, clientType={}, success={}, "
                        + "errorCode={}, costMs={}",
                result.getActionCode(), result.getCapabilityVersion(), result.getClientType(),
                result.isSuccess(), result.getErrorCode(),
                System.currentTimeMillis() - startTime);
        return result;
    }

    private CapabilityToolErrorCode transportError(Exception failure) {
        if (failure instanceof io.grpc.StatusRuntimeException rpc) {
            if (rpc.getStatus().getCode() == io.grpc.Status.Code.DEADLINE_EXCEEDED) return CapabilityToolErrorCode.TRANSPORT_TIMEOUT;
            if (rpc.getStatus().getCode() == io.grpc.Status.Code.RESOURCE_EXHAUSTED) return CapabilityToolErrorCode.RESPONSE_TOO_LARGE;
        }
        return CapabilityToolErrorCode.TRANSPORT_ERROR;
    }

    /**
     * 使用与真实执行完全相同的校验、映射和环境路由生成瞬时请求预览，不发起 RPC。
     *
     * <p>不包含传输凭据；身份在独立 Protobuf context 中由宿主注入。
     */
    public CapabilityActionExecutionPreview preview(CapabilityActionExecutionPlan executionPlan,
            String toolInput, ToolContext toolContext, ReleaseEnvironment requestedEnvironment,
            ReleaseEnvironment resolvedEnvironment) {
        return prepare(executionPlan, toolInput, toolContext,
                requestedEnvironment, resolvedEnvironment).preview();
    }

    private PreparedExecution prepare(CapabilityActionExecutionPlan executionPlan,
            String toolInput, ToolContext toolContext, ReleaseEnvironment requestedEnvironment,
            ReleaseEnvironment resolvedEnvironment) {
        validateEnvironments(requestedEnvironment, resolvedEnvironment);
        BaseAgentContext agentContext = requireAgentContext(toolContext);
        validatePlan(executionPlan, toolContext);
        Map<String, Object> arguments = parseArguments(toolInput);
        validateArguments(executionPlan, arguments);
        arguments.replaceAll((field, value) -> CapabilityIntegerSupport.normalize(value,
                (executionPlan.getArgumentSchemas() == null
                        ? Collections.<String, Map<String, Object>>emptyMap()
                        : executionPlan.getArgumentSchemas()).getOrDefault(field,
                        Map.of("type", executionPlan.getArgumentTypes().get(field)))));
        Map<String, Object> requestBody = buildRequestBody(executionPlan, arguments, agentContext);
        rpcContext(agentContext, toolContext, resolvedEnvironment);
        CapabilityActionExecutionPreview preview = CapabilityActionExecutionPreview.builder()
                .protocol("GRPC").targetKey(executionPlan.getTargetKey())
                .serviceName(executionPlan.getServiceName()).methodName(executionPlan.getMethodName())
                .effectiveArguments(new LinkedHashMap<>(arguments))
                .effectiveRequestBody(new LinkedHashMap<>(requestBody))
                .cookieInjected(false)
                .build();
        return new PreparedExecution(preview);
    }

    private dev.a2flow.management.capabilityrpc.CapabilityRpcContext rpcContext(BaseAgentContext agent,
            ToolContext context, ReleaseEnvironment environment) {
        if (agent.getUserId() == null) throw failure(CapabilityToolErrorCode.TRUSTED_CONTEXT_REQUIRED, "userId required");
        return new dev.a2flow.management.capabilityrpc.CapabilityRpcContext(agent.getUserId(), environment,
                trustedString(context, TrustedToolContext.TRACE_ID), agent.getClient());
    }

    private void validateEnvironments(ReleaseEnvironment requestedEnvironment,
            ReleaseEnvironment resolvedEnvironment) {
        if (requestedEnvironment == null) {
            throw failure(CapabilityToolErrorCode.RELEASE_ENVIRONMENT_REQUIRED,
                    "trusted releaseEnvironment is required");
        }
        if (resolvedEnvironment == null) {
            throw failure(CapabilityToolErrorCode.RELEASE_ENVIRONMENT_INVALID,
                    "resolved capability environment is required");
        }
        if (requestedEnvironment != resolvedEnvironment) throw failure(CapabilityToolErrorCode.RELEASE_ENVIRONMENT_INVALID,
                "Cross-environment capability fallback forbidden");
    }

    private void validatePlan(CapabilityActionExecutionPlan executionPlan, ToolContext toolContext) {
        if (executionPlan == null) {
            throw failure(CapabilityToolErrorCode.EXECUTION_PLAN_INVALID,
                    "capability execution plan is required");
        }
        if (!"GRPC".equals(executionPlan.getBindingType())) {
            throw failure(CapabilityToolErrorCode.EXECUTION_PLAN_INVALID,
                    "unsupported capability binding type");
        }
        if (!"GRPC".equals(executionPlan.getSourceType())) {
            throw failure(CapabilityToolErrorCode.EXECUTION_PLAN_INVALID,
                    "unsupported capability sourceType");
        }
        if (executionPlan.getMaxResponseBytes() <= 0 || executionPlan.getTimeoutMs() <= 0) {
            throw failure(CapabilityToolErrorCode.EXECUTION_PLAN_INVALID,
                    "controlled HTTP execution policy is invalid");
        }
    }

    /** 只接受宿主可信上下文中的审核结论；普通业务参数或模型 Tool 入参不能授予副作用权限。 */
    private boolean reviewedDemoApproved(ToolContext toolContext) {
        if (toolContext == null || toolContext.getContext() == null) {
            return false;
        }
        return Boolean.TRUE.equals(
                toolContext.getContext().get(TrustedToolContext.REVIEWED_DEMO_APPROVED));
    }

    private BaseAgentContext requireAgentContext(ToolContext toolContext) {
        if (toolContext == null || toolContext.getContext() == null) {
            throw failure(CapabilityToolErrorCode.TRUSTED_CONTEXT_REQUIRED,
                    "trusted toolContext is required");
        }
        Object contextValue = toolContext.getContext().get(FIELD_AGENT_CONTEXT);
        if (!(contextValue instanceof BaseAgentContext)) {
            throw failure(CapabilityToolErrorCode.TRUSTED_CONTEXT_REQUIRED,
                    "trusted agentContext is required");
        }
        return (BaseAgentContext) contextValue;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseArguments(String toolInput) {
        if (StringUtils.isBlank(toolInput)) {
            return new LinkedHashMap<>();
        }
        try {
            Object value = JsonSupport.fromJSON(toolInput, Object.class);
            if (!(value instanceof Map)) {
                throw new IllegalArgumentException("tool arguments must be a JSON object");
            }
            return new LinkedHashMap<>((Map<String, Object>) value);
        } catch (Exception exception) {
            throw failure(CapabilityToolErrorCode.ARGUMENT_INVALID,
                    "tool arguments must be a valid JSON object");
        }
    }

    private void validateArguments(CapabilityActionExecutionPlan executionPlan,
            Map<String, Object> arguments) {
        for (Map.Entry<String, Object> argument : arguments.entrySet()) {
            String field = argument.getKey();
            String normalized = StringUtils.lowerCase(field, Locale.ROOT);
            if (FORBIDDEN_ARGUMENTS.contains(normalized)
                    || !executionPlan.getModelArgumentFields().contains(field)) {
                throw failure(CapabilityToolErrorCode.ARGUMENT_INVALID,
                        "入参未声明或不允许由调用方传入：" + field
                                + "。请检查示例入参与模型入参定义是否一致；固定参数应配置在请求映射中。");
            }
            Map<String, Map<String, Object>> argumentSchemas = executionPlan.getArgumentSchemas();
            Map<String, Object> argumentSchema = argumentSchemas == null
                    ? Collections.emptyMap() : argumentSchemas.get(field);
            validateArgumentType(field, argument.getValue(),
                    executionPlan.getArgumentTypes().get(field), argumentSchema);
            validateAllowedArgumentValue(executionPlan, field, argument.getValue());
        }
        for (String requiredField : executionPlan.getRequiredArgumentFields()) {
            if (!arguments.containsKey(requiredField) || arguments.get(requiredField) == null) {
                throw failure(CapabilityToolErrorCode.ARGUMENT_INVALID,
                        "缺少必填入参：" + requiredField);
            }
        }
    }

    private void validateArgumentType(String field, Object value, String expectedType,
            Map<String, Object> schema) {
        if (value == null) {
            return;
        }
        boolean matched = switch (StringUtils.defaultString(expectedType)) {
            case "string" -> value instanceof String;
            case "number" -> value instanceof Number;
            case "integer" -> CapabilityIntegerSupport.isInteger(value);
            case "boolean" -> value instanceof Boolean;
            case "object" -> value instanceof Map;
            case "array" -> value instanceof List;
            default -> false;
        };
        if (!matched) {
            throw failure(CapabilityToolErrorCode.ARGUMENT_TYPE_MISMATCH,
                    "入参类型与能力定义不一致：" + field);
        }
        if ("array".equals(expectedType)) {
            Map<String, Object> items = mapValue(schema == null ? null : schema.get(FIELD_ITEMS));
            List<?> values = (List<?>) value;
            for (int index = 0; index < values.size(); index++) {
                validateSchemaValue(field + "[" + index + "]", values.get(index), items);
            }
        }
    }

    /** 递归校验数组元素与对象字段；所有失败均在构造 HTTP 请求之前返回精确路径。 */
    private void validateSchemaValue(String path, Object value, Map<String, Object> schema) {
        if (value == null) {
            return;
        }
        String type = String.valueOf(schema.get(FIELD_TYPE));
        boolean matched = "string".equals(type) ? value instanceof String
                : "number".equals(type) ? value instanceof Number
                : "integer".equals(type) ? CapabilityIntegerSupport.isInteger(value)
                : "boolean".equals(type) ? value instanceof Boolean
                : "array".equals(type) ? value instanceof List
                : "object".equals(type) && value instanceof Map;
        if (!matched) {
            throw failure(CapabilityToolErrorCode.ARGUMENT_TYPE_MISMATCH,
                    "入参类型与能力定义不一致：" + path);
        }
        if ("array".equals(type)) {
            Map<String, Object> items = mapValue(schema.get(FIELD_ITEMS));
            List<?> values = (List<?>) value;
            for (int index = 0; index < values.size(); index++) {
                validateSchemaValue(path + "[" + index + "]", values.get(index), items);
            }
            return;
        }
        if (!"object".equals(type)) {
            return;
        }
        Map<String, Object> objectValue = mapValue(value);
        Map<String, Object> properties = mapValue(schema.get(FIELD_PROPERTIES));
        Object requiredValue = schema.get(FIELD_REQUIRED);
        if (requiredValue instanceof List) {
            for (Object requiredField : (List<?>) requiredValue) {
                if (!objectValue.containsKey(requiredField) || objectValue.get(requiredField) == null) {
                    throw failure(CapabilityToolErrorCode.ARGUMENT_INVALID,
                            "缺少必填入参：" + path + "." + requiredField);
                }
            }
        }
        for (Map.Entry<String, Object> entry : objectValue.entrySet()) {
            Map<String, Object> propertySchema = mapValue(properties.get(entry.getKey()));
            if (propertySchema.isEmpty()) {
                throw failure(CapabilityToolErrorCode.ARGUMENT_INVALID,
                        "入参中包含未声明的字段：" + path + "." + entry.getKey());
            }
            validateSchemaValue(path + "." + entry.getKey(), entry.getValue(), propertySchema);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    /** 发布枚举是执行门禁；unit/label/description 均不参与请求参数。 */
    private void validateAllowedArgumentValue(CapabilityActionExecutionPlan executionPlan,
            String field, Object value) {
        Map<String, List<Object>> constraints = executionPlan.getAllowedArgumentValues();
        List<Object> allowedValues = constraints == null ? null : constraints.get(field);
        if (value == null || allowedValues == null || allowedValues.isEmpty()) {
            return;
        }
        String type = executionPlan.getArgumentTypes().get(field);
        boolean matched = allowedValues.stream().anyMatch(allowedValue ->
                typedValuesEqual(allowedValue, value, type));
        if (!matched) {
            throw failure(CapabilityToolErrorCode.ARGUMENT_INVALID,
                    "入参取值不在能力定义的允许范围内：" + field);
        }
    }

    private boolean typedValuesEqual(Object left, Object right, String type) {
        if (StringUtils.equalsAny(type, "number", "integer")
                && left instanceof Number && right instanceof Number) {
            return new BigDecimal(String.valueOf(left))
                    .compareTo(new BigDecimal(String.valueOf(right))) == 0;
        }
        return left != null && left.equals(right);
    }

    private Map<String, Object> buildRequestBody(CapabilityActionExecutionPlan executionPlan,
            Map<String, Object> arguments, BaseAgentContext agentContext) {
        Map<String, Object> requestBody = new LinkedHashMap<>();
        executionPlan.getRequestMappings().forEach((toolField, requestPath) -> {
            if (arguments.containsKey(toolField)) {
                putPath(requestBody, requestPath, arguments.get(toolField));
            }
        });
        executionPlan.getContextMappings().forEach((requestPath, contextField) -> {
            Object contextValue = requireContextValue(agentContext, contextField);
            putPath(requestBody, requestPath,
                    mapContextValue(executionPlan, requestPath, contextField, contextValue));
        });
        executionPlan.getConstantMappings().forEach((requestPath, value) -> putPath(requestBody, requestPath, value));
        return requestBody;
    }

    private Object requireContextValue(BaseAgentContext agentContext, String contextField) {
        if (StringUtils.equals(contextField, "userId")) {
            return dev.a2flow.management.access.UserIds.toWire(agentContext.getUserId());
        }
        if (StringUtils.equals(contextField, "client")) {
            return requiredContextValue(contextField, agentContext.getClient());
        }
        if (StringUtils.equals(contextField, "env")) {
            return requiredContextValue(contextField, agentContext.getEnv());
        }
        throw failure(CapabilityToolErrorCode.REQUEST_MAPPING_INVALID, "Only userId/client/env trusted mappings allowed");
    }

    /**
     * 对可信系统变量执行发布态显式值映射；配置映射后未命中时必须失败，不能把错误枚举透传给业务接口。
     */
    private Object mapContextValue(CapabilityActionExecutionPlan executionPlan, String requestPath,
            String contextField, Object contextValue) {
        Map<String, Map<String, String>> valueMappings = executionPlan.getContextValueMappings();
        Map<String, String> valueMapping = valueMappings == null ? null : valueMappings.get(requestPath);
        if (valueMapping == null || valueMapping.isEmpty()) {
            return contextValue;
        }
        String mappedValue = valueMapping.get(String.valueOf(contextValue));
        if (mappedValue == null) {
            throw failure(CapabilityToolErrorCode.REQUEST_MAPPING_INVALID,
                    "system variable value mapping is missing: " + contextField);
        }
        return mappedValue;
    }

    private Object requiredContextValue(String field, Object value) {
        if (value == null || StringUtils.isBlank(String.valueOf(value))) {
            throw failure(CapabilityToolErrorCode.TRUSTED_CONTEXT_REQUIRED,
                    "runtime context is missing: " + field);
        }
        return value;
    }

    @SuppressWarnings("unchecked")
    private void putPath(Map<String, Object> target, String path, Object value) {
        if (StringUtils.isBlank(path) || !REQUEST_PATH_PATTERN.matcher(path).matches()) {
            throw failure(CapabilityToolErrorCode.REQUEST_MAPPING_INVALID,
                    "request mapping path is invalid");
        }
        String[] segments = path.split("\\.");
        Map<String, Object> current = target;
        for (int index = 0; index < segments.length - 1; index++) {
            Object child = current.get(segments[index]);
            if (child == null) {
                Map<String, Object> next = new LinkedHashMap<>();
                current.put(segments[index], next);
                current = next;
                continue;
            }
            if (!(child instanceof Map)) {
                throw failure(CapabilityToolErrorCode.REQUEST_MAPPING_INVALID,
                        "request mapping path conflicts with a scalar field");
            }
            current = (Map<String, Object>) child;
        }
        String leaf = segments[segments.length - 1];
        if (current.containsKey(leaf)) {
            throw failure(CapabilityToolErrorCode.REQUEST_MAPPING_INVALID,
                    "request mapping writes the same target more than once");
        }
        current.put(leaf, value);
    }

    private CapabilityToolResult failure(CapabilityActionExecutionPlan executionPlan,
            ReleaseEnvironment requestedEnvironment, ReleaseEnvironment resolvedEnvironment,
            String traceId, CapabilityToolErrorCode errorCode, String message) {
        return CapabilityToolResult.builder()
                .success(false)
                .actionCode(actionCode(executionPlan))
                .sourceId(executionPlan == null ? null : executionPlan.getSourceId())
                .sourceDigest(executionPlan == null ? null : executionPlan.getSourceDigest())
                .capabilityVersion(executionPlan == null ? 0 : executionPlan.getCapabilityVersion())
                .clientType(executionPlan == null ? StringUtils.EMPTY : executionPlan.getClientType())
                .requestedEnvironment(requestedEnvironment)
                .resolvedEnvironment(resolvedEnvironment)
                .httpStatus(0)
                .contentType(StringUtils.EMPTY)
                .traceId(StringUtils.defaultString(traceId))
                .data(null)
                .errorCode(errorCode)
                .message(message)
                .build();
    }

    private String actionCode(CapabilityActionExecutionPlan executionPlan) {
        return executionPlan == null ? StringUtils.EMPTY : executionPlan.getActionCode();
    }

    private String sourceId(CapabilityActionExecutionPlan executionPlan) {
        return executionPlan == null ? StringUtils.EMPTY : executionPlan.getSourceId();
    }

    private String trustedString(ToolContext toolContext, String key) {
        if (toolContext == null || toolContext.getContext() == null) {
            return StringUtils.EMPTY;
        }
        Object value = toolContext.getContext().get(key);
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }

    private CapabilityExecutionException failure(CapabilityToolErrorCode errorCode, String message) {
        return new CapabilityExecutionException(errorCode, message);
    }

    private record PreparedExecution(CapabilityActionExecutionPreview preview) {
    }

    /** 可安全返回调用方的执行校验错误，仅携带错误码和字段说明，不携带参数值或凭证。 */
    public static final class CapabilityExecutionException extends RuntimeException {

        private final CapabilityToolErrorCode errorCode;

        public CapabilityExecutionException(CapabilityToolErrorCode errorCode, String message) {
            super(message);
            this.errorCode = errorCode;
        }

        public CapabilityToolErrorCode getErrorCode() {
            return errorCode;
        }
    }
}
