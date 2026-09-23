package dev.a2flow.management.agentcore.runtime.tool;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.tool.ComponentToolContractService.ComponentContractException;
import dev.a2flow.management.model.ComponentToolErrorCode;
import dev.a2flow.management.release.ReleaseEnvironment;

import lombok.extern.slf4j.Slf4j;

/**
 * 批量查询当前环境组件契约的固定 Tool。
 *
 * <p>模型只提交最多 20 个 componentName；可信环境和 userId 由 Agent 宿主通过 ToolContext 注入。
 * 结果按首次出现顺序逐项返回，重复名称只查询一次，单项失败不阻断同批其它组件。本 Tool 不列举完整
 * Registry、不执行渲染，也不返回 bundle、模板、动作配置、资产 ID、版本或传输信息。
 */
@Component
@Slf4j
public class QueryComponentToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "query_component";

    private static final String FIELD_COMPONENT_NAME_LIST = "componentNameList";
    private static final String FIELD_COMPONENT_NAME = "componentName";
    private static final String FIELD_SUCCESS = "success";
    private static final String FIELD_REQUESTED_COUNT = "requestedCount";
    private static final String FIELD_RESOLVED_COUNT = "resolvedCount";
    private static final String FIELD_RESULTS = "results";
    private static final String FIELD_ERROR_CODE = "errorCode";
    private static final String FIELD_MESSAGE = "message";
    private static final int MAX_COMPONENT_COUNT = 20;
    private static final int MAX_COMPONENT_NAME_LENGTH = 128;
    private static final String ERROR_RELEASE_UNRESOLVED = "component release cannot be resolved";
    private static final String ERROR_ARGUMENT_INVALID =
            "query_component input must contain 1 to 20 valid componentNameList values";
    private static final String ERROR_ENVIRONMENT_REQUIRED = "trusted releaseEnvironment is required";
    private static final String ERROR_ENVIRONMENT_INVALID =
            "trusted releaseEnvironment must be PRT or ONLINE";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "componentNameList": {
                  "type": "array",
                  "description": "Component names compiled into the current Skill",
                  "minItems": 1,
                  "maxItems": 20,
                  "uniqueItems": true,
                  "items": {"type": "string", "minLength": 1, "maxLength": 128}
                }
              },
              "required": ["componentNameList"],
              "additionalProperties": false
            }
            """;

    @Resource
    private ComponentToolContractService componentToolContractService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_NAME)
                .description("Batch query the current-environment render_component contracts. "
                        + "Pass all component names needed in this turn, then render with the returned "
                        + "paramsSchemaJson and renderArgumentsExample.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /**
     * 在可信环境下按输入顺序批量解析组件契约；单项异常转换为结构化结果并继续处理下一项。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        List<String> componentNames;
        ReleaseEnvironment requestedEnvironment;
        try {
            componentNames = parseComponentNames(toolInput);
            requestedEnvironment = requireReleaseEnvironment(toolContext);
        } catch (ComponentQueryException exception) {
            return failure(exception.getErrorCode(), exception.getMessage());
        }
        Long userId = trustedUserId(toolContext);
        List<Map<String, Object>> results = new ArrayList<>();
        int resolvedCount = 0;
        for (String componentName : componentNames) {
            try {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put(FIELD_SUCCESS, true);
                item.putAll(componentToolContractService.query(
                        componentName, requestedEnvironment, userId));
                results.add(item);
                resolvedCount++;
            } catch (ComponentContractException exception) {
                results.add(itemFailure(componentName, exception.getErrorCode(), exception.getMessage()));
            } catch (Exception exception) {
                log.warn("组件Tool批量查询单项异常, componentName:{}, requestedEnvironment:{}",
                        componentName, requestedEnvironment, exception);
                results.add(itemFailure(componentName,
                        ComponentToolErrorCode.COMPONENT_RELEASE_NOT_AVAILABLE,
                        ERROR_RELEASE_UNRESOLVED));
            }
        }
        Map<String, Object> response = new LinkedHashMap<>();
        response.put(FIELD_SUCCESS, resolvedCount == componentNames.size());
        response.put(FIELD_REQUESTED_COUNT, componentNames.size());
        response.put(FIELD_RESOLVED_COUNT, resolvedCount);
        response.put(FIELD_RESULTS, results);
        log.info("组件Tool批量查询完成, requestedEnvironment:{}, requestedCount:{}, resolvedCount:{}",
                requestedEnvironment, componentNames.size(), resolvedCount);
        return JsonSupport.toJSON(response);
    }

    @SuppressWarnings("unchecked")
    private List<String> parseComponentNames(String toolInput) {
        try {
            Object parsed = JsonSupport.fromJSON(toolInput, Object.class);
            if (!(parsed instanceof Map<?, ?>)) {
                throw argumentFailure();
            }
            Map<String, Object> input = (Map<String, Object>) parsed;
            if (input.size() != 1 || !(input.get(FIELD_COMPONENT_NAME_LIST) instanceof List<?> values)
                    || values.isEmpty() || values.size() > MAX_COMPONENT_COUNT) {
                throw argumentFailure();
            }
            Set<String> componentNames = new LinkedHashSet<>();
            for (Object value : values) {
                if (!(value instanceof String)) {
                    throw argumentFailure();
                }
                String componentName = StringUtils.trim((String) value);
                if (StringUtils.isBlank(componentName)
                        || componentName.length() > MAX_COMPONENT_NAME_LENGTH) {
                    throw argumentFailure();
                }
                componentNames.add(componentName);
            }
            return new ArrayList<>(componentNames);
        } catch (ComponentQueryException exception) {
            throw exception;
        } catch (Exception exception) {
            throw argumentFailure();
        }
    }

    private ReleaseEnvironment requireReleaseEnvironment(ToolContext toolContext) {
        Object value = contextValue(toolContext, TrustedToolContext.RELEASE_ENVIRONMENT);
        if (!(value instanceof String) || StringUtils.isBlank(String.valueOf(value))) {
            throw new ComponentQueryException(ComponentToolErrorCode.RELEASE_ENVIRONMENT_REQUIRED,
                    ERROR_ENVIRONMENT_REQUIRED);
        }
        try {
            return ReleaseEnvironment.valueOf(String.valueOf(value));
        } catch (IllegalArgumentException exception) {
            throw new ComponentQueryException(ComponentToolErrorCode.RELEASE_ENVIRONMENT_INVALID,
                    ERROR_ENVIRONMENT_INVALID);
        }
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

    private Object contextValue(ToolContext toolContext, String key) {
        return toolContext == null || toolContext.getContext() == null
                ? null : toolContext.getContext().get(key);
    }

    private Map<String, Object> itemFailure(String componentName,
            ComponentToolErrorCode errorCode, String message) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put(FIELD_SUCCESS, false);
        item.put(FIELD_COMPONENT_NAME, componentName);
        item.put(FIELD_ERROR_CODE, errorCode);
        item.put(FIELD_MESSAGE, message);
        return item;
    }

    private String failure(ComponentToolErrorCode errorCode, String message) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_SUCCESS, false);
        result.put(FIELD_REQUESTED_COUNT, 0);
        result.put(FIELD_RESOLVED_COUNT, 0);
        result.put(FIELD_RESULTS, List.of());
        result.put(FIELD_ERROR_CODE, errorCode);
        result.put(FIELD_MESSAGE, message);
        return JsonSupport.toJSON(result);
    }

    private ComponentQueryException argumentFailure() {
        return new ComponentQueryException(ComponentToolErrorCode.ARGUMENT_INVALID,
                ERROR_ARGUMENT_INVALID);
    }

    /** 顶层参数或可信环境错误。 */
    private static final class ComponentQueryException extends IllegalArgumentException {

        private final ComponentToolErrorCode errorCode;

        private ComponentQueryException(ComponentToolErrorCode errorCode, String message) {
            super(message);
            this.errorCode = errorCode;
        }

        private ComponentToolErrorCode getErrorCode() {
            return errorCode;
        }
    }
}
