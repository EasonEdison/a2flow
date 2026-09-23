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
import dev.a2flow.management.agentcore.runtime.tool
        .A2uiApplicationToolContractService.A2uiApplicationContractException;
import dev.a2flow.management.agentcore.runtime.tool
        .ComponentToolContractService.ComponentContractException;
import dev.a2flow.management.model.A2uiApplicationToolErrorCode;
import dev.a2flow.management.model.CapabilityToolErrorCode;
import dev.a2flow.management.model.ComponentToolErrorCode;
import dev.a2flow.management.release.ReleaseEnvironment;

import lombok.extern.slf4j.Slf4j;

/**
 * 聚合查询当前可信环境下 CARD 组件、A2UI Application 与业务能力契约的固定 Tool。
 *
 * <p>上游模型显式提交本轮需要的 componentName/appCode/actionCode 列表，本类按三类稳定身份校验、
 * 去重并保持首次出现顺序。环境与 userId 只从 ToolContext 读取；本类不按名称推断类型、不调用其它
 * ToolCallback，也不执行渲染、能力、审批或绑定动作。结果不增加资产 ID、发布来源、URL、Header、
 * 凭证等运行时敏感事实。
 */
@Component
@Slf4j
public class QuerySkillDependenciesToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "query_skill_dependencies";

    private static final String FIELD_COMPONENT_NAME_LIST = "componentNameList";
    private static final String FIELD_A2UI_APPLICATION_CODE_LIST = "a2uiApplicationCodeList";
    private static final String FIELD_ACTION_CODE_LIST = "actionCodeList";
    private static final String FIELD_COMPONENT_NAME = "componentName";
    private static final String FIELD_APP_CODE = "appCode";
    private static final String FIELD_STATUS = "status";
    private static final String FIELD_SUCCESS = "success";
    private static final String FIELD_COMPONENTS = "components";
    private static final String FIELD_A2UI_APPLICATIONS = "a2uiApplications";
    private static final String FIELD_BUSINESS_CAPABILITIES = "businessCapabilities";
    private static final String FIELD_RESULTS = "results";
    private static final String FIELD_REQUESTED_COUNT = "requestedCount";
    private static final String FIELD_AVAILABLE_COUNT = "availableCount";
    private static final String FIELD_UNAVAILABLE_COUNT = "unavailableCount";
    private static final String FIELD_ERROR_CODE = "errorCode";
    private static final String FIELD_MESSAGE = "message";
    private static final String STATUS_AVAILABLE = "AVAILABLE";
    private static final String CLIENT_PC = "PC";
    private static final String CLIENT_APP = "APP";
    private static final int MAX_COMPONENT_COUNT = 20;
    private static final int MAX_A2UI_APPLICATION_COUNT = 20;
    private static final int MAX_ACTION_CODE_COUNT = 50;
    private static final int MAX_COMPONENT_NAME_LENGTH = 128;
    private static final String ERROR_ARGUMENT_INVALID =
            "query_skill_dependencies requires 1 to 20 component names, 1 to 20 A2UI app codes, "
                    + "or 1 to 50 action codes";
    private static final String ERROR_ENVIRONMENT_REQUIRED = "trusted releaseEnvironment is required";
    private static final String ERROR_ENVIRONMENT_INVALID =
            "trusted releaseEnvironment must be PRT or ONLINE";
    private static final String ERROR_COMPONENT_RELEASE_UNRESOLVED =
            "component release cannot be resolved";
    private static final String ERROR_A2UI_APPLICATION_RELEASE_UNRESOLVED =
            "A2UI Application release cannot be resolved";
    private static final String ERROR_CAPABILITY_RELEASE_UNRESOLVED =
            "business capability catalog cannot be resolved";
    private static final String ERROR_CAPABILITY_RELEASE_UNAVAILABLE =
            "business capability release is not available in trusted environment";
    private static final String ERROR_TRUSTED_CLIENT_TYPE = "trusted clientType must be PC or APP";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "componentNameList": {
                  "type": "array",
                  "minItems": 1,
                  "maxItems": 20,
                  "items": {"type": "string", "minLength": 1, "maxLength": 128},
                  "description": "Component names whose current render contracts are required"
                },
                "a2uiApplicationCodeList": {
                  "type": "array",
                  "minItems": 1,
                  "maxItems": 20,
                  "items": {"type": "string", "minLength": 1, "maxLength": 128},
                  "description": "A2UI Application app codes whose current input contracts are required"
                },
                "actionCodeList": {
                  "type": "array",
                  "minItems": 1,
                  "maxItems": 50,
                  "items": {"type": "string", "minLength": 1},
                  "description": "Business action codes whose full model-facing contracts are required"
                }
              },
              "anyOf": [
                {"required": ["componentNameList"]},
                {"required": ["a2uiApplicationCodeList"]},
                {"required": ["actionCodeList"]}
              ],
              "additionalProperties": false
            }
            """;

    @Resource
    private ComponentToolContractService componentToolContractService;

    @Resource
    private A2uiApplicationToolContractService a2uiApplicationToolContractService;

    @Resource
    private CapabilityCatalogQueryService capabilityCatalogQueryService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_NAME)
                .description("Batch query current-environment CARD component, A2UI Application, and business "
                        + "capability contracts. Use the matching list before render_component, "
                        + "render_a2ui_application, or execute_business_capability; this query does not grant "
                        + "binding, approval, or execution authority.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /** 解析显式依赖列表，并使用可信环境一次返回三类当前契约。 */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        DependencyQueryRequest request;
        ReleaseEnvironment requestedEnvironment;
        try {
            request = parseInput(toolInput);
            requestedEnvironment = requireReleaseEnvironment(toolContext);
        } catch (DependencyQueryException exception) {
            return failure(exception.errorCode, exception.getMessage());
        }
        Long userId = trustedUserId(toolContext);
        String clientType;
        try {
            clientType = requireClientType(toolContext);
        } catch (DependencyQueryException exception) {
            return failure(exception.errorCode, exception.getMessage());
        }
        try {
            DependencySection components = queryComponents(
                    request.componentNames, requestedEnvironment, userId);
            DependencySection a2uiApplications = queryA2uiApplications(
                    request.a2uiApplicationCodes, requestedEnvironment, userId);
            DependencySection capabilities = queryCapabilities(
                    request.actionCodes, requestedEnvironment, userId, clientType);
            Map<String, Object> result = new LinkedHashMap<>();
            result.put(FIELD_SUCCESS, components.unavailableCount == 0
                    && a2uiApplications.unavailableCount == 0
                    && capabilities.unavailableCount == 0);
            result.put(FIELD_COMPONENTS, components.toMap());
            result.put(FIELD_A2UI_APPLICATIONS, a2uiApplications.toMap());
            result.put(FIELD_BUSINESS_CAPABILITIES, capabilities.toMap());
            log.info("Skill依赖聚合查询完成, requestedEnvironment:{}, componentRequested:{}, "
                            + "componentAvailable:{}, a2uiApplicationRequested:{}, "
                            + "a2uiApplicationAvailable:{}, capabilityRequested:{}, capabilityAvailable:{}",
                    requestedEnvironment, components.requestedCount, components.availableCount,
                    a2uiApplications.requestedCount, a2uiApplications.availableCount,
                    capabilities.requestedCount, capabilities.availableCount);
            return JsonSupport.toJSON(result);
        } catch (CapabilityCatalogQueryService.CapabilityCatalogException exception) {
            return failure(exception.getErrorCode(), exception.getMessage());
        } catch (Exception exception) {
            log.warn("Skill依赖聚合查询失败, requestedEnvironment:{}, errorType:{}",
                    requestedEnvironment, exception.getClass().getSimpleName());
            return failure(CapabilityToolErrorCode.CAPABILITY_RELEASE_NOT_AVAILABLE,
                    ERROR_CAPABILITY_RELEASE_UNRESOLVED);
        }
    }

    private DependencySection queryComponents(List<String> componentNames,
            ReleaseEnvironment requestedEnvironment, Long userId) {
        List<Map<String, Object>> results = new ArrayList<>();
        int availableCount = 0;
        for (String componentName : componentNames) {
            try {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put(FIELD_SUCCESS, true);
                item.putAll(componentToolContractService.query(
                        componentName, requestedEnvironment, userId));
                results.add(item);
                availableCount++;
            } catch (ComponentContractException exception) {
                results.add(itemFailure(componentName, FIELD_COMPONENT_NAME,
                        exception.getErrorCode(), exception.getMessage()));
            } catch (Exception exception) {
                log.warn("Skill依赖聚合查询组件失败, componentName:{}, requestedEnvironment:{}, "
                                + "errorType:{}",
                        componentName, requestedEnvironment, exception.getClass().getSimpleName());
                results.add(itemFailure(componentName, FIELD_COMPONENT_NAME,
                        ComponentToolErrorCode.COMPONENT_RELEASE_NOT_AVAILABLE,
                        ERROR_COMPONENT_RELEASE_UNRESOLVED));
            }
        }
        return new DependencySection(componentNames.size(), availableCount, results);
    }

    private DependencySection queryCapabilities(List<String> actionCodes,
            ReleaseEnvironment requestedEnvironment, Long userId, String clientType) {
        if (actionCodes.isEmpty()) {
            return DependencySection.empty();
        }
        List<Map<String, Object>> results = new ArrayList<>();
        int availableCount = 0;
        for (Map<String, Object> capability : capabilityCatalogQueryService.queryByActionCodes(
                actionCodes, requestedEnvironment, userId, clientType)) {
            boolean available = StringUtils.equals(
                    STATUS_AVAILABLE, String.valueOf(capability.get(FIELD_STATUS)));
            Map<String, Object> item = new LinkedHashMap<>();
            item.put(FIELD_SUCCESS, available);
            item.putAll(capability);
            if (!available) {
                item.putIfAbsent(FIELD_MESSAGE, ERROR_CAPABILITY_RELEASE_UNAVAILABLE);
            }
            results.add(item);
            if (available) {
                availableCount++;
            }
        }
        return new DependencySection(actionCodes.size(), availableCount, results);
    }

    private DependencySection queryA2uiApplications(List<String> appCodes,
            ReleaseEnvironment requestedEnvironment, Long userId) {
        List<Map<String, Object>> results = new ArrayList<>();
        int availableCount = 0;
        for (String appCode : appCodes) {
            try {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put(FIELD_SUCCESS, true);
                item.putAll(a2uiApplicationToolContractService.query(
                        appCode, requestedEnvironment, userId));
                results.add(item);
                availableCount++;
            } catch (A2uiApplicationContractException exception) {
                results.add(itemFailure(appCode, FIELD_APP_CODE,
                        exception.getErrorCode(), exception.getMessage()));
            } catch (Exception exception) {
                log.warn("Skill依赖聚合查询A2UI Application失败, appCode:{}, "
                                + "requestedEnvironment:{}, errorType:{}",
                        appCode, requestedEnvironment, exception.getClass().getSimpleName());
                results.add(itemFailure(appCode, FIELD_APP_CODE,
                        A2uiApplicationToolErrorCode.A2UI_APPLICATION_RELEASE_NOT_AVAILABLE,
                        ERROR_A2UI_APPLICATION_RELEASE_UNRESOLVED));
            }
        }
        return new DependencySection(appCodes.size(), availableCount, results);
    }

    @SuppressWarnings("unchecked")
    private DependencyQueryRequest parseInput(String toolInput) {
        try {
            Object parsed = JsonSupport.fromJSON(toolInput, Object.class);
            if (!(parsed instanceof Map<?, ?>)) {
                throw argumentFailure();
            }
            Map<String, Object> input = (Map<String, Object>) parsed;
            if (input.isEmpty() || input.size() > 3
                    || input.keySet().stream().anyMatch(key -> !StringUtils.equals(key,
                            FIELD_COMPONENT_NAME_LIST)
                            && !StringUtils.equals(key, FIELD_A2UI_APPLICATION_CODE_LIST)
                            && !StringUtils.equals(key, FIELD_ACTION_CODE_LIST))) {
                throw argumentFailure();
            }
            List<String> componentNames = parseList(input, FIELD_COMPONENT_NAME_LIST,
                    MAX_COMPONENT_COUNT, true);
            List<String> a2uiApplicationCodes = parseList(input, FIELD_A2UI_APPLICATION_CODE_LIST,
                    MAX_A2UI_APPLICATION_COUNT, true);
            List<String> actionCodes = parseList(input, FIELD_ACTION_CODE_LIST,
                    MAX_ACTION_CODE_COUNT, false);
            if (componentNames.isEmpty() && a2uiApplicationCodes.isEmpty() && actionCodes.isEmpty()) {
                throw argumentFailure();
            }
            return new DependencyQueryRequest(componentNames, a2uiApplicationCodes, actionCodes);
        } catch (DependencyQueryException exception) {
            throw exception;
        } catch (Exception exception) {
            throw argumentFailure();
        }
    }

    private List<String> parseList(Map<String, Object> input, String field, int maxCount,
            boolean validateComponentNameLength) {
        if (!input.containsKey(field)) {
            return List.of();
        }
        Object value = input.get(field);
        if (!(value instanceof List<?> values) || values.isEmpty() || values.size() > maxCount) {
            throw argumentFailure();
        }
        Set<String> result = new LinkedHashSet<>();
        for (Object item : values) {
            if (!(item instanceof String)) {
                throw argumentFailure();
            }
            String normalized = StringUtils.trim((String) item);
            if (StringUtils.isBlank(normalized)
                    || validateComponentNameLength && normalized.length() > MAX_COMPONENT_NAME_LENGTH) {
                throw argumentFailure();
            }
            result.add(normalized);
        }
        return new ArrayList<>(result);
    }

    private ReleaseEnvironment requireReleaseEnvironment(ToolContext toolContext) {
        Object value = contextValue(toolContext, TrustedToolContext.RELEASE_ENVIRONMENT);
        if (!(value instanceof String) || StringUtils.isBlank(String.valueOf(value))) {
            throw new DependencyQueryException(
                    CapabilityToolErrorCode.RELEASE_ENVIRONMENT_REQUIRED, ERROR_ENVIRONMENT_REQUIRED);
        }
        try {
            return ReleaseEnvironment.valueOf(String.valueOf(value));
        } catch (IllegalArgumentException exception) {
            throw new DependencyQueryException(
                    CapabilityToolErrorCode.RELEASE_ENVIRONMENT_INVALID, ERROR_ENVIRONMENT_INVALID);
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

    private String requireClientType(ToolContext toolContext) {
        Object value = contextValue(toolContext, TrustedToolContext.CLIENT_TYPE);
        String clientType = StringUtils.upperCase(StringUtils.trimToEmpty(
                value == null ? StringUtils.EMPTY : String.valueOf(value)));
        if (!StringUtils.equalsAny(clientType, CLIENT_PC, CLIENT_APP)) {
            throw new DependencyQueryException(
                    CapabilityToolErrorCode.CAPABILITY_CLIENT_NOT_SUPPORTED,
                    ERROR_TRUSTED_CLIENT_TYPE);
        }
        return clientType;
    }

    private Object contextValue(ToolContext toolContext, String key) {
        return toolContext == null || toolContext.getContext() == null
                ? null : toolContext.getContext().get(key);
    }

    private Map<String, Object> itemFailure(String identity, String identityField,
            Enum<?> errorCode, String message) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put(FIELD_SUCCESS, false);
        item.put(identityField, identity);
        item.put(FIELD_ERROR_CODE, errorCode);
        item.put(FIELD_MESSAGE, message);
        return item;
    }

    private String failure(CapabilityToolErrorCode errorCode, String message) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_SUCCESS, false);
        result.put(FIELD_COMPONENTS, DependencySection.empty().toMap());
        result.put(FIELD_A2UI_APPLICATIONS, DependencySection.empty().toMap());
        result.put(FIELD_BUSINESS_CAPABILITIES, DependencySection.empty().toMap());
        result.put(FIELD_ERROR_CODE, errorCode);
        result.put(FIELD_MESSAGE, message);
        return JsonSupport.toJSON(result);
    }

    private DependencyQueryException argumentFailure() {
        return new DependencyQueryException(CapabilityToolErrorCode.ARGUMENT_INVALID,
                ERROR_ARGUMENT_INVALID);
    }

    /** 经过校验、去重且保持首次出现顺序的三类查询请求。 */
    private static final class DependencyQueryRequest {
        private final List<String> componentNames;
        private final List<String> a2uiApplicationCodes;
        private final List<String> actionCodes;

        private DependencyQueryRequest(List<String> componentNames,
                List<String> a2uiApplicationCodes, List<String> actionCodes) {
            this.componentNames = componentNames;
            this.a2uiApplicationCodes = a2uiApplicationCodes;
            this.actionCodes = actionCodes;
        }
    }

    /** 一类依赖的明细与数量摘要。 */
    private static final class DependencySection {
        private final int requestedCount;
        private final int availableCount;
        private final int unavailableCount;
        private final List<Map<String, Object>> results;

        private DependencySection(int requestedCount, int availableCount,
                List<Map<String, Object>> results) {
            this.requestedCount = requestedCount;
            this.availableCount = availableCount;
            this.unavailableCount = requestedCount - availableCount;
            this.results = results;
        }

        private static DependencySection empty() {
            return new DependencySection(0, 0, List.of());
        }

        private Map<String, Object> toMap() {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put(FIELD_REQUESTED_COUNT, requestedCount);
            result.put(FIELD_AVAILABLE_COUNT, availableCount);
            result.put(FIELD_UNAVAILABLE_COUNT, unavailableCount);
            result.put(FIELD_RESULTS, results);
            return result;
        }
    }

    /** 顶层输入或可信上下文不满足契约时的稳定错误。 */
    private static final class DependencyQueryException extends IllegalArgumentException {
        private final CapabilityToolErrorCode errorCode;

        private DependencyQueryException(CapabilityToolErrorCode errorCode, String message) {
            super(message);
            this.errorCode = errorCode;
        }
    }
}
