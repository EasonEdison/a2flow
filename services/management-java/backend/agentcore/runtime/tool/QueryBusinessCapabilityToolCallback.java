package dev.a2flow.management.agentcore.runtime.tool;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.model.CapabilityToolErrorCode;
import dev.a2flow.management.release.ReleaseEnvironment;

/**
 * 查询当前可信环境下已发布的业务能力目录。
 *
 * <p>按 businessDomain 返回精简发现信息，按 actionCodeList 批量返回模型调用契约。环境和 userId
 * 只从可信 ToolContext 读取，响应不暴露稳定资产 ID、版本指针、URL、Header 或凭证。
 */
@Component
public class QueryBusinessCapabilityToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "query_business_capability";

    private static final String FIELD_BUSINESS_DOMAIN = "businessDomain";
    private static final String FIELD_ACTION_CODE_LIST = "actionCodeList";
    private static final String MODE_BUSINESS_DOMAIN = "BUSINESS_DOMAIN";
    private static final String MODE_ACTION_CODE_LIST = "ACTION_CODE_LIST";
    private static final String CLIENT_PC = "PC";
    private static final String CLIENT_APP = "APP";
    private static final String ERROR_TRUSTED_CLIENT_TYPE = "trusted clientType must be PC or APP";
    private static final int MAX_ACTION_CODE_COUNT = 50;
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "businessDomain": {
                  "type": "string",
                  "description": "Business domain used to discover actionCode, Chinese name and business description"
                },
                "actionCodeList": {
                  "type": "array",
                  "items": {"type": "string"},
                  "minItems": 1,
                  "maxItems": 50,
                  "description": "Action codes whose full model-facing contracts are required"
                }
              },
              "oneOf": [
                {"required": ["businessDomain"]},
                {"required": ["actionCodeList"]}
              ],
              "additionalProperties": false
            }
            """;

    @Resource
    private CapabilityCatalogQueryService capabilityCatalogQueryService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_NAME)
                .description("Discover released business capabilities by businessDomain, or batch load full "
                        + "model-facing contracts by actionCodeList before execution.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /** 使用可信环境查询目录，并保持两种选择器严格互斥。 */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        try {
            QueryRequest request = parseInput(toolInput);
            ReleaseEnvironment requestedEnvironment = requireReleaseEnvironment(toolContext);
            Long userId = trustedUserId(toolContext);
            String clientType = requireClientType(toolContext);
            List<Map<String, Object>> capabilities = request.businessDomain == null
                    ? capabilityCatalogQueryService.queryByActionCodes(
                            request.actionCodes, requestedEnvironment, userId, clientType)
                    : capabilityCatalogQueryService.queryByBusinessDomain(
                            request.businessDomain, requestedEnvironment, userId, clientType);
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("success", true);
            result.put("mode", request.businessDomain == null
                    ? MODE_ACTION_CODE_LIST : MODE_BUSINESS_DOMAIN);
            result.put("capabilities", capabilities);
            return JsonSupport.toJSON(result);
        } catch (CapabilityCatalogQueryService.CapabilityCatalogException exception) {
            return failure(exception.getErrorCode(), exception.getMessage());
        } catch (CapabilityContextException exception) {
            return failure(exception.errorCode(), exception.getMessage());
        } catch (Exception exception) {
            return failure(CapabilityToolErrorCode.CAPABILITY_RELEASE_NOT_AVAILABLE,
                    "business capability catalog cannot be resolved");
        }
    }

    @SuppressWarnings("unchecked")
    private QueryRequest parseInput(String toolInput) {
        try {
            Object parsed = JsonSupport.fromJSON(toolInput, Object.class);
            if (!(parsed instanceof Map)) {
                throw new IllegalArgumentException("tool input must be object");
            }
            Map<String, Object> input = (Map<String, Object>) parsed;
            boolean hasBusinessDomain = input.containsKey(FIELD_BUSINESS_DOMAIN);
            boolean hasActionCodeList = input.containsKey(FIELD_ACTION_CODE_LIST);
            if (input.size() != 1 || hasBusinessDomain == hasActionCodeList) {
                throw new IllegalArgumentException("exactly one query selector is required");
            }
            if (hasBusinessDomain) {
                Object value = input.get(FIELD_BUSINESS_DOMAIN);
                if (!(value instanceof String) || StringUtils.isBlank((String) value)) {
                    throw new IllegalArgumentException("businessDomain must be non-blank string");
                }
                return QueryRequest.byBusinessDomain(StringUtils.trim((String) value));
            }
            Object value = input.get(FIELD_ACTION_CODE_LIST);
            if (!(value instanceof List) || ((List<?>) value).isEmpty()
                    || ((List<?>) value).size() > MAX_ACTION_CODE_COUNT) {
                throw new IllegalArgumentException("actionCodeList size is invalid");
            }
            List<String> actionCodes = new ArrayList<>();
            for (Object actionCode : (List<?>) value) {
                if (!(actionCode instanceof String) || StringUtils.isBlank((String) actionCode)) {
                    throw new IllegalArgumentException("actionCodeList item must be non-blank string");
                }
                actionCodes.add(StringUtils.trim((String) actionCode));
            }
            return QueryRequest.byActionCodes(actionCodes);
        } catch (CapabilityContextException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new CapabilityContextException(CapabilityToolErrorCode.ARGUMENT_INVALID,
                    StringUtils.defaultIfBlank(exception.getMessage(),
                            "query_business_capability input is invalid"));
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

    private String trustedString(ToolContext toolContext, String key) {
        Object value = contextValue(toolContext, key);
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }

    private String failure(CapabilityToolErrorCode errorCode, String message) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("success", false);
        result.put("capabilities", List.of());
        result.put("errorCode", errorCode);
        result.put("message", message);
        return JsonSupport.toJSON(result);
    }

    private static final class QueryRequest {
        private final String businessDomain;
        private final List<String> actionCodes;

        private QueryRequest(String businessDomain, List<String> actionCodes) {
            this.businessDomain = businessDomain;
            this.actionCodes = actionCodes;
        }

        private static QueryRequest byBusinessDomain(String businessDomain) {
            return new QueryRequest(businessDomain, List.of());
        }

        private static QueryRequest byActionCodes(List<String> actionCodes) {
            return new QueryRequest(null, actionCodes);
        }
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
