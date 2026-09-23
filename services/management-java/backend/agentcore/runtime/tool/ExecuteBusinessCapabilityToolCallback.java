package dev.a2flow.management.agentcore.runtime.tool;

import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.model.CapabilityToolErrorCode;
import dev.a2flow.management.model.CapabilityToolResult;
import dev.a2flow.management.release.ReleaseEnvironment;

/**
 * 平台固定业务能力执行 Tool。
 *
 * <p>模型只提交 actionCode 和业务 arguments。本类按可信环境目录把 actionCode 映射到唯一稳定能力
 * 身份，并在每次调用时重新解析不可变发布源；模型不能覆盖环境、版本、目标地址、Header 或认证信息。
 */
@Component
public class ExecuteBusinessCapabilityToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "execute_business_capability";

    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_ARGUMENTS = "arguments";
    private static final String CLIENT_PC = "PC";
    private static final String CLIENT_APP = "APP";
    private static final String ERROR_TRUSTED_CLIENT_TYPE = "trusted clientType must be PC or APP";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "actionCode": {
                  "type": "string",
                  "description": "Action code whose contract was refreshed by query_skill_dependencies"
                },
                "arguments": {
                  "type": "object",
                  "description": "Business arguments matching the selected capability inputSchema"
                }
              },
              "required": ["actionCode", "arguments"],
              "additionalProperties": false
            }
            """;

    @Resource
    private CapabilityActionToolProvider capabilityActionToolProvider;

    @Resource
    private CapabilityCatalogQueryService capabilityCatalogQueryService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_NAME)
                .description("Execute one released business capability in the trusted environment. "
                        + "Call query_skill_dependencies first; query_business_capability remains available "
                        + "for domain discovery. Only provide actionCode plus business arguments.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /**
     * 使用可信环境目录解析唯一稳定身份，再委托通用执行器执行不可变发布态。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        String actionCode = StringUtils.EMPTY;
        ReleaseEnvironment requestedEnvironment = null;
        try {
            Map<String, Object> input = parseInput(toolInput);
            actionCode = String.valueOf(input.get(FIELD_ACTION_CODE));
            requestedEnvironment = requireReleaseEnvironment(toolContext);
            Long userId = trustedUserId(toolContext);
            String clientType = requireClientType(toolContext);
            String assetKey = capabilityCatalogQueryService.requireAssetKey(
                    actionCode, requestedEnvironment, userId, clientType);
            ToolCallback releasedCallback = capabilityActionToolProvider.createReleased(
                    assetKey, requestedEnvironment, userId, clientType);
            return releasedCallback.call(JsonSupport.toJSON(input.get(FIELD_ARGUMENTS)), toolContext);
        } catch (CapabilityCatalogQueryService.CapabilityCatalogException exception) {
            return failure(actionCode, requestedEnvironment, toolContext,
                    exception.getErrorCode(), exception.getMessage());
        } catch (CapabilityContextException exception) {
            return failure(actionCode, requestedEnvironment, toolContext,
                    exception.errorCode(), exception.getMessage());
        } catch (Exception exception) {
            return failure(actionCode, requestedEnvironment, toolContext,
                    CapabilityToolErrorCode.CAPABILITY_RELEASE_NOT_AVAILABLE,
                    "business capability release cannot be resolved or compiled");
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseInput(String toolInput) {
        try {
            Object parsed = JsonSupport.fromJSON(toolInput, Object.class);
            if (!(parsed instanceof Map)) {
                throw new IllegalArgumentException("tool input must be object");
            }
            Map<String, Object> input = (Map<String, Object>) parsed;
            if (input.size() != 2 || !input.containsKey(FIELD_ACTION_CODE)
                    || !input.containsKey(FIELD_ARGUMENTS)
                    || StringUtils.isBlank(String.valueOf(input.get(FIELD_ACTION_CODE)))
                    || !(input.get(FIELD_ARGUMENTS) instanceof Map)) {
                throw new IllegalArgumentException("tool input shape is invalid");
            }
            return input;
        } catch (Exception exception) {
            throw new CapabilityContextException(CapabilityToolErrorCode.ARGUMENT_INVALID,
                    "execute_business_capability input is invalid");
        }
    }

    private ReleaseEnvironment requireReleaseEnvironment(ToolContext toolContext) {
        Object value = contextValue(toolContext, TrustedToolContext.RELEASE_ENVIRONMENT);
        if (!(value instanceof String) || StringUtils.isBlank(String.valueOf(value))) {
            throw new CapabilityContextException(CapabilityToolErrorCode.RELEASE_ENVIRONMENT_REQUIRED,
                    "trusted releaseEnvironment is required");
        }
        try {
            return ReleaseEnvironment.valueOf(String.valueOf(value));
        } catch (IllegalArgumentException exception) {
            throw new CapabilityContextException(CapabilityToolErrorCode.RELEASE_ENVIRONMENT_INVALID,
                    "trusted releaseEnvironment must be PRT or ONLINE");
        }
    }

    private Object contextValue(ToolContext toolContext, String key) {
        return toolContext == null || toolContext.getContext() == null
                ? null : toolContext.getContext().get(key);
    }

    private String failure(String actionCode, ReleaseEnvironment requestedEnvironment, ToolContext toolContext,
            CapabilityToolErrorCode errorCode, String message) {
        CapabilityToolResult result = CapabilityToolResult.builder()
                .success(false)
                .actionCode(actionCode)
                .capabilityVersion(0)
                .clientType(trustedString(toolContext, TrustedToolContext.CLIENT_TYPE))
                .requestedEnvironment(requestedEnvironment)
                .resolvedEnvironment(null)
                .httpStatus(0)
                .contentType(StringUtils.EMPTY)
                .traceId(trustedString(toolContext, TrustedToolContext.TRACE_ID))
                .data(null)
                .errorCode(errorCode)
                .message(message)
                .build();
        return JsonSupport.toJSON(result);
    }

    private String trustedString(ToolContext toolContext, String key) {
        Object value = contextValue(toolContext, key);
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }

    private Long trustedUserId(ToolContext toolContext) {
        Object value = contextValue(toolContext, TrustedToolContext.USER_ID);
        if (value == null) {
            return null;
        }
        if (!(value instanceof Long)) {
            throw new IllegalArgumentException("Trusted userId must be a Long");
        }
        return (Long) value;
    }

    private String requireClientType(ToolContext toolContext) {
        String clientType = StringUtils.upperCase(StringUtils.trimToEmpty(
                trustedString(toolContext, TrustedToolContext.CLIENT_TYPE)));
        if (!StringUtils.equalsAny(clientType, CLIENT_PC, CLIENT_APP)) {
            throw new CapabilityContextException(CapabilityToolErrorCode.CAPABILITY_CLIENT_NOT_SUPPORTED,
                    ERROR_TRUSTED_CLIENT_TYPE);
        }
        return clientType;
    }

    private static final class CapabilityContextException extends RuntimeException {

        private final CapabilityToolErrorCode errorCode;

        private CapabilityContextException(CapabilityToolErrorCode errorCode, String message) {
            super(message);
            this.errorCode = errorCode;
        }

        private CapabilityToolErrorCode errorCode() {
            return errorCode;
        }
    }
}
