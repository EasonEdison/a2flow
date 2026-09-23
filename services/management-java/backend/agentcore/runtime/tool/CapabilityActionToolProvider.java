package dev.a2flow.management.agentcore.runtime.tool;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.model.CapabilityActionExecutionPlan;
import dev.a2flow.management.model.CapabilityActionExecutionPreview;
import dev.a2flow.management.model.CapabilityIntegerSupport;
import dev.a2flow.management.release.CapabilityReleasePayloadAdapter;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetResolutionContext;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyType;
import dev.a2flow.management.release.dependency.EnvironmentAwareAssetResolver;

import lombok.extern.slf4j.Slf4j;

/**
 * 业务能力执行计划构建器。
 *
 * <p>该组件按稳定 assetKey 和可信环境解析不可变发布源，再把能力 payload 编译成执行计划，
 * 交给平台固定业务能力 Tool 执行。actionCode 只标识具体能力，不为每项能力注册独立 Tool 或 Spring Bean。
 */
@Component
@Slf4j
public class CapabilityActionToolProvider {

    private static final String SIDE_EFFECT_READ = "READ";
    private static final String FIELD_BASIC_INFO = "basicInfo";
    private static final String FIELD_SUPPORTED_CLIENTS = "supportedClients";
    private static final String FIELD_CLIENT_VARIANTS = "clientVariants";
    private static final String FIELD_MODEL_CONTRACT = "modelContract";
    private static final String FIELD_RESULT_CONTRACT = "resultContract";
    private static final String FIELD_EXECUTION_BINDING = "executionBinding";
    private static final String FIELD_GOVERNANCE = "governance";
    private static final String FIELD_API_SOURCE = "apiSource";
    private static final String FIELD_SOURCE_TYPE = "sourceType";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_DESCRIPTION = "description";
    private static final String FIELD_INPUT_FIELDS = "inputFields";
    private static final String FIELD_REQUIRED = "required";
    private static final String FIELD_TOOL_FIELD = "toolField";
    private static final String FIELD_BUSINESS_MEANING = "businessMeaning";
    private static final String FIELD_UNIT = "unit";
    private static final String FIELD_EXAMPLES = "examples";
    private static final String FIELD_ALLOWED_VALUES = "allowedValues";
    private static final String FIELD_VALUE = "value";
    private static final String FIELD_LABEL = "label";
    private static final String FIELD_ENUM = "enum";
    private static final String FIELD_ITEMS = "items";
    private static final String FIELD_PROPERTIES = "properties";
    private static final String FIELD_ADDITIONAL_PROPERTIES = "additionalProperties";
    private static final String FIELD_FIELD_SOURCE = "source";
    private static final String FIELD_SOURCE_MODEL_INPUT = "MODEL_INPUT";
    private static final String FIELD_SOURCE_CONSTANT = "CONSTANT";
    private static final String FIELD_SOURCE_SYSTEM_VARIABLE = "SYSTEM_VARIABLE";
    private static final String FIELD_CONSTANT_VALUE = "constantValue";
    private static final String FIELD_SYSTEM_VARIABLE = "systemVariable";
    private static final String FIELD_VALUE_MAPPING = "valueMapping";
    private static final String SYSTEM_VARIABLE_USER_ID = "userId";
    private static final String SYSTEM_VARIABLE_CLIENT = "client";
    private static final String FIELD_KEY_OUTPUT_FIELDS = "keyOutputFields";
    private static final String FIELD_OBSERVED_TYPE = "observedType";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_BINDING_TYPE = "bindingType";
    private static final String FIELD_TARGET = "target";
    private static final String FIELD_PATH = "path";
    private static final String FIELD_TIMEOUT_MS = "timeoutMs";
    private static final String FIELD_MAX_RESPONSE_BYTES = "maxResponseBytes";
    private static final String FIELD_REQUEST_MAPPINGS_JSON = "requestMappingsJson";
    private static final String FIELD_CONTEXT_MAPPINGS_JSON = "contextMappingsJson";
    private static final String FIELD_SIDE_EFFECT_LEVEL = "sideEffectLevel";
    private static final int DEFAULT_TIMEOUT_MS = 3000;
    private static final int MAX_TIMEOUT_MS = 120000;
    private static final int DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024;
    private static final int MAX_RESPONSE_BYTES = 5 * 1024 * 1024;
    private static final String CLIENT_PC = "PC";
    private static final String CLIENT_APP = "APP";
    private static final String CLIENT_COMMON = "COMMON";
    private static final List<String> CLIENT_MODE_PC = List.of(CLIENT_PC);
    private static final List<String> CLIENT_MODE_APP = List.of(CLIENT_APP);
    private static final List<String> CLIENT_MODE_DIFFERENT = List.of(CLIENT_PC, CLIENT_APP);
    private static final List<String> CLIENT_MODE_COMMON = List.of(CLIENT_COMMON);
    private static final String ERROR_CLIENT_REQUIRED = "capability clientType is required";
    private static final String ERROR_CLIENT_NOT_SUPPORTED = "CAPABILITY_CLIENT_NOT_SUPPORTED";
    private static final String ERROR_SUPPORTED_CLIENTS_INVALID = "supportedClients is invalid";
    private static final String ERROR_CLIENT_VARIANTS_MISMATCH =
            "supportedClients and clientVariants do not match";
    private static final String IDEMPOTENCY_NONE = "NONE";
    private static final String DEFAULT_RESPONSE_POLICY = "ORIGINAL";
    private static final String SUCCESS_STATUS_2XX = "2XX";
    private static final int HTTP_STATUS_MIN = 100;
    private static final int HTTP_STATUS_MAX = 599;
    private static final int HTTP_SUCCESS_STATUS_MIN = 200;
    private static final int HTTP_SUCCESS_STATUS_MAX = 299;
    private static final int DIGEST_LOG_PREFIX_LENGTH = 12;

    @Resource
    private CapabilityActionExecutor capabilityActionExecutor;

    @Resource
    private EnvironmentAwareAssetResolver environmentAwareAssetResolver;

    @Resource
    private CapabilityReleasePayloadAdapter capabilityReleasePayloadAdapter;

    /**
     * 从已保存能力快照创建动态 ToolCallback。
     */
    public ToolCallback create(CapabilityActionDraft draft, ReleaseEnvironment resolvedEnvironment,
            String clientType) {
        if (resolvedEnvironment == null) {
            throw new IllegalArgumentException("resolved capability environment is required");
        }
        CapabilityActionExecutionPlan executionPlan = compile(draft, 0, clientType);
        return new ResolvedCapabilityActionToolCallback(
                executionPlan, capabilityActionExecutor, resolvedEnvironment, resolvedEnvironment);
    }

    /**
     * 为能力中心直接验证生成与真实执行一致的瞬时安全请求预览，不执行 HTTP。
     */
    public CapabilityActionExecutionPreview preview(CapabilityActionDraft draft,
            ReleaseEnvironment resolvedEnvironment, String clientType, Map<String, Object> arguments,
            ToolContext toolContext) {
        if (resolvedEnvironment == null) {
            throw new IllegalArgumentException("resolved capability environment is required");
        }
        CapabilityActionExecutionPlan executionPlan = compile(draft, 0, clientType);
        return capabilityActionExecutor.preview(executionPlan,
                JsonSupport.toJSON(arguments == null ? Collections.emptyMap() : arguments),
                toolContext, resolvedEnvironment, resolvedEnvironment);
    }

    /**
     * 按稳定能力 ID 和调用方可信环境解析不可变发布源，再创建运行态 ToolCallback。
     */
    public ToolCallback createReleased(String assetKey, ReleaseEnvironment requestedEnvironment,
            String clientType) {
        return createReleased(assetKey, requestedEnvironment, null, clientType);
    }

    /** 按可信环境和 userId 解析灰度后的不可变能力版本。 */
    public ToolCallback createReleased(String assetKey, ReleaseEnvironment requestedEnvironment,
            Long userId, String clientType) {
        if (StringUtils.isBlank(assetKey) || requestedEnvironment == null) {
            throw new IllegalArgumentException("capability assetKey and requestedEnvironment are required");
        }
        ResolvedReleasedAsset resolvedAsset = environmentAwareAssetResolver.resolve(
                new AssetDependencyReference()
                        .setAssetType(AssetDependencyType.CAPABILITY_ACTION)
                        .setAssetKey(assetKey),
                new AssetResolutionContext()
                        .setRequestedEnvironment(requestedEnvironment)
                        .setUserId(userId));
        CapabilityActionDraft draft = capabilityReleasePayloadAdapter.requireExecutableDraft(resolvedAsset);
        CapabilityActionExecutionPlan executionPlan = compile(draft, resolvedAsset.getVersion(), clientType);
        log.info("业务能力运行态发布源解析完成, assetKey:{}, requestedEnvironment:{}, "
                        + "clientType:{}, resolvedEnvironment:{}, sourceType:{}, sourceId:{}, version:{}, candidate:{}, "
                        + "routeReason:{}, digestPrefix:{}",
                assetKey, requestedEnvironment, executionPlan.getClientType(), resolvedAsset.getResolvedEnvironment(),
                resolvedAsset.getSourceType(), resolvedAsset.getSourceId(), resolvedAsset.getVersion(),
                resolvedAsset.getCandidate(), resolvedAsset.getRouteReason(),
                StringUtils.left(StringUtils.defaultString(resolvedAsset.getDigest()), DIGEST_LOG_PREFIX_LENGTH));
        return new ResolvedCapabilityActionToolCallback(executionPlan, capabilityActionExecutor,
                requestedEnvironment, resolvedAsset.getResolvedEnvironment());
    }

    /**
     * 按稳定能力 ID 解析当前环境下的不可变执行计划，供固定查询 Tool 展示模型可见契约。
     */
    public CapabilityActionExecutionPlan resolveReleasedPlan(String assetKey,
            ReleaseEnvironment requestedEnvironment, String clientType) {
        return resolveReleasedPlan(assetKey, requestedEnvironment, null, clientType);
    }

    /** 按可信环境和 userId 解析模型可见能力契约，保证查询与执行命中同一版本。 */
    public CapabilityActionExecutionPlan resolveReleasedPlan(String assetKey,
            ReleaseEnvironment requestedEnvironment, Long userId, String clientType) {
        if (StringUtils.isBlank(assetKey) || requestedEnvironment == null) {
            throw new IllegalArgumentException("capability assetKey and requestedEnvironment are required");
        }
        ResolvedReleasedAsset resolvedAsset = environmentAwareAssetResolver.resolve(
                new AssetDependencyReference()
                        .setAssetType(AssetDependencyType.CAPABILITY_ACTION)
                        .setAssetKey(assetKey),
                new AssetResolutionContext()
                        .setRequestedEnvironment(requestedEnvironment)
                        .setUserId(userId));
        CapabilityActionDraft draft = capabilityReleasePayloadAdapter.requireExecutableDraft(resolvedAsset);
        if (resolvedAsset.getResolvedEnvironment() != requestedEnvironment) {
            throw new IllegalArgumentException("CAPABILITY_RELEASE_NOT_AVAILABLE: cross-environment fallback forbidden");
        }
        return compile(draft, resolvedAsset.getVersion(), clientType).toBuilder()
                .sourceId(resolvedAsset.getSourceId()).sourceDigest(resolvedAsset.getDigest())
                .resolvedEnvironment(resolvedAsset.getResolvedEnvironment()).build();
    }

    /**
     * 将 canonical draft 编译为不可变受控 HTTP 执行计划。
     */
    public CapabilityActionExecutionPlan compile(CapabilityActionDraft draft, String clientType) {
        return compile(draft, 0, clientType);
    }

    private CapabilityActionExecutionPlan compile(CapabilityActionDraft draft,
            Integer capabilityVersion, String requestedClientType) {
        if (draft == null || draft.getDraft() == null) {
            throw new IllegalArgumentException("capability draft is required");
        }
        String clientType = requireClientType(requestedClientType);
        Map<String, Object> root = draft.getDraft();
        Map<String, Object> basicInfo = mapValue(root.get(FIELD_BASIC_INFO));
        ClientVariantSelection clientVariantSelection = requireClientVariant(root, clientType);
        Map<String, Object> variant = clientVariantSelection.variant;
        Map<String, Object> apiSource = mapValue(variant.get(FIELD_API_SOURCE));
        Map<String, Object> modelContract = mapValue(variant.get(FIELD_MODEL_CONTRACT));
        Map<String, Object> resultContract = mapValue(variant.get(FIELD_RESULT_CONTRACT));
        Map<String, Object> executionBinding = mapValue(variant.get(FIELD_EXECUTION_BINDING));
        Map<String, Object> governance = mapValue(root.get(FIELD_GOVERNANCE));
        Map<String, Object> target = mapValue(executionBinding.get(FIELD_TARGET));

        String sourceType = required(apiSource, FIELD_SOURCE_TYPE);
        if (!"GRPC".equals(sourceType)) throw new IllegalArgumentException("Only GRPC sourceType is supported");
        String clusterCode = null;
        String bindingType = required(executionBinding, FIELD_BINDING_TYPE);
        if (!"GRPC".equals(bindingType)) throw new IllegalArgumentException("Only GRPC bindingType is supported");
        dev.a2flow.management.capabilityrpc.GrpcCapabilityContract.validateBinding(executionBinding);
        String actionCode = required(basicInfo, FIELD_ACTION_CODE);

        List<Map<String, Object>> inputFields = listOfMaps(modelContract.get(FIELD_INPUT_FIELDS));
        List<String> inputFieldNames = inputFieldNames(inputFields);
        List<String> modelArgumentFields = new ArrayList<>();
        List<String> requiredArgumentFields = new ArrayList<>();
        Map<String, String> argumentTypes = new LinkedHashMap<>();
        Map<String, Map<String, Object>> argumentSchemas = new LinkedHashMap<>();
        Map<String, List<Object>> allowedArgumentValues = new LinkedHashMap<>();
        String inputSchema = buildInputSchema(
                inputFields, modelArgumentFields, requiredArgumentFields,
                argumentTypes, argumentSchemas, allowedArgumentValues);
        Map<String, String> staticHeaders = Collections.emptyMap();
        Map<String, Map<String, String>> environmentHeaders = Collections.emptyMap();
        Map<String, String> allRequestMappings = stringMap(executionBinding.get(FIELD_REQUEST_MAPPINGS_JSON),
                FIELD_REQUEST_MAPPINGS_JSON);
        validateRequestMappings(inputFieldNames, allRequestMappings);
        Map<String, String> requestMappings = modelRequestMappings(modelArgumentFields, allRequestMappings);
        Map<String, String> contextMappings = stringMap(
                executionBinding.get(FIELD_CONTEXT_MAPPINGS_JSON), FIELD_CONTEXT_MAPPINGS_JSON);
        Map<String, Map<String, String>> contextValueMappings = compileContextValueMappings(
                inputFields, allRequestMappings);
        Map<String, Object> constantMappings = compileConstantMappings(inputFields, allRequestMappings);
        validateMappingTargets(requestMappings, contextMappings, constantMappings);

        String idempotency = IDEMPOTENCY_NONE;
        String responsePolicy = DEFAULT_RESPONSE_POLICY;
        String sideEffectLevel = StringUtils.defaultIfBlank(
                stringValue(governance.get(FIELD_SIDE_EFFECT_LEVEL)), SIDE_EFFECT_READ);
        return CapabilityActionExecutionPlan.builder()
                .sourceId(draft.getDraftId())
                .revision(draft.getRevision() == null ? 0 : draft.getRevision())
                .capabilityVersion(capabilityVersion == null ? 0 : capabilityVersion)
                .clientType(clientType)
                .contractClientType(clientVariantSelection.contractClientType)
                .actionCode(actionCode)
                .toolDescription(buildToolDescription(basicInfo, modelContract))
                .inputSchema(inputSchema)
                .keyOutputFields(immutableKeyOutputFields(resultContract.get(FIELD_KEY_OUTPUT_FIELDS)))
                .sourceType(sourceType)
                .targetKey(required(target, "targetKey"))
                .serviceName(required(target, "serviceName"))
                .methodName(required(target, "methodName"))
                .descriptorSetBase64(required(target, "descriptorSetBase64"))
                .contextField(required(target, "contextField"))
                .technicalOutputSchema(required(resultContract, "technicalOutputSchema"))
                .clusterCode(clusterCode)
                .bindingType(bindingType)
                .timeoutMs(timeoutMs(executionBinding.get(FIELD_TIMEOUT_MS)))
                .maxResponseBytes(maxResponseBytes(executionBinding.get(FIELD_MAX_RESPONSE_BYTES)))
                .successStatusCodes(Collections.emptySet())
                .idempotency(idempotency)
                .responsePolicy(responsePolicy)
                .sideEffectLevel(sideEffectLevel)
                .modelArgumentFields(List.copyOf(modelArgumentFields))
                .requiredArgumentFields(List.copyOf(requiredArgumentFields))
                .argumentTypes(unmodifiableMap(argumentTypes))
                .argumentSchemas(unmodifiableSchemaMap(argumentSchemas))
                .allowedArgumentValues(unmodifiableListMap(allowedArgumentValues))
                .staticHeaders(unmodifiableMap(staticHeaders))
                .environmentHeaders(unmodifiableNestedMap(environmentHeaders))
                .requestMappings(unmodifiableMap(requestMappings))
                .contextMappings(unmodifiableMap(contextMappings))
                .contextValueMappings(unmodifiableNestedMap(contextValueMappings))
                .constantMappings(unmodifiableObjectMap(constantMappings))
                .build();
    }

    /**
     * 校验四种 canonical 形态并选择显式契约。
     *
     * <p>可信 PC/APP 在 COMMON 模式下选择唯一 COMMON 契约；这是发布声明的确定性选择，不应用
     * PC/APP 优先级，也不在具体端契约缺失时尝试其他具体端。作者态 COMMON dry-run 仅选择 COMMON。
     */
    private ClientVariantSelection requireClientVariant(Map<String, Object> root, String clientType) {
        Object supportedValue = root.get(FIELD_SUPPORTED_CLIENTS);
        if (!(supportedValue instanceof List)) {
            throw new CapabilityClientNotSupportedException(clientType);
        }
        List<String> supportedClients = ((List<?>) supportedValue).stream()
                .map(this::stringValue)
                .toList();
        if (!isCanonicalClientMode(supportedClients)) {
            throw new IllegalArgumentException(ERROR_SUPPORTED_CLIENTS_INVALID);
        }
        Map<String, Object> variants = mapValue(root.get(FIELD_CLIENT_VARIANTS));
        if (!new ArrayList<>(variants.keySet()).equals(supportedClients)) {
            throw new IllegalArgumentException(ERROR_CLIENT_VARIANTS_MISMATCH);
        }
        String contractClientType = CLIENT_MODE_COMMON.equals(supportedClients)
                ? CLIENT_COMMON : clientType;
        Object selectedVariant = variants.get(contractClientType);
        if ((!supportedClients.contains(clientType) && !CLIENT_MODE_COMMON.equals(supportedClients))
                || !(selectedVariant instanceof Map)) {
            throw new CapabilityClientNotSupportedException(clientType);
        }
        return new ClientVariantSelection(contractClientType, mapValue(selectedVariant));
    }

    private boolean isCanonicalClientMode(List<String> supportedClients) {
        return CLIENT_MODE_PC.equals(supportedClients) || CLIENT_MODE_APP.equals(supportedClients)
                || CLIENT_MODE_DIFFERENT.equals(supportedClients)
                || CLIENT_MODE_COMMON.equals(supportedClients);
    }

    private String requireClientType(String clientType) {
        String normalized = StringUtils.upperCase(StringUtils.trimToEmpty(clientType), Locale.ROOT);
        if (!StringUtils.equalsAny(normalized, CLIENT_PC, CLIENT_APP, CLIENT_COMMON)) {
            throw new IllegalArgumentException(ERROR_CLIENT_REQUIRED);
        }
        return normalized;
    }

    /** 实际可信端与所选发布契约键分离，避免 COMMON 覆盖运行态 client 系统变量。 */
    private static final class ClientVariantSelection {

        private final String contractClientType;
        private final Map<String, Object> variant;

        private ClientVariantSelection(String contractClientType, Map<String, Object> variant) {
            this.contractClientType = contractClientType;
            this.variant = variant;
        }
    }

    /** 精确端契约缺失的稳定异常，供目录和执行 Tool 映射统一错误码。 */
    public static class CapabilityClientNotSupportedException extends IllegalArgumentException {

        private final String clientType;

        private CapabilityClientNotSupportedException(String clientType) {
            super(ERROR_CLIENT_NOT_SUPPORTED + ": " + clientType);
            this.clientType = clientType;
        }

        public String getClientType() {
            return clientType;
        }
    }

    private String buildInputSchema(List<Map<String, Object>> inputFields, List<String> modelArgumentFields,
            List<String> requiredArgumentFields, Map<String, String> argumentTypes,
            Map<String, Map<String, Object>> argumentSchemas,
            Map<String, List<Object>> allowedArgumentValues) {
        Map<String, Object> properties = new LinkedHashMap<>();
        for (Map<String, Object> field : inputFields) {
            if (!FIELD_SOURCE_MODEL_INPUT.equals(stringValue(field.get(FIELD_FIELD_SOURCE)))) {
                continue;
            }
            String toolField = required(field, FIELD_TOOL_FIELD);
            modelArgumentFields.add(toolField);
            String fieldType = jsonSchemaType(stringValue(field.get(FIELD_TYPE)));
            Map<String, Object> fieldSchema = compileInputSchema(field, true);
            argumentTypes.put(toolField, fieldType);
            argumentSchemas.put(toolField, fieldSchema);
            List<Object> allowedValues = compileAllowedValues(field, fieldType);
            if (!allowedValues.isEmpty()) {
                fieldSchema.put(FIELD_ENUM, allowedValues);
                allowedArgumentValues.put(toolField, allowedValues);
            }
            properties.put(toolField, fieldSchema);
            if (Boolean.TRUE.equals(field.get(FIELD_REQUIRED))) {
                requiredArgumentFields.add(toolField);
            }
        }
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put(FIELD_TYPE, "object");
        schema.put(FIELD_PROPERTIES, properties);
        schema.put(FIELD_REQUIRED, requiredArgumentFields);
        schema.put(FIELD_ADDITIONAL_PROPERTIES, false);
        return JsonSupport.toJSON(schema);
    }

    /** 把 canonical 字段或 items 节点编译为闭合 JSON Schema。 */
    private Map<String, Object> compileInputSchema(Map<String, Object> source, boolean topLevel) {
        String type = topLevel
                ? jsonSchemaType(stringValue(source.get(FIELD_TYPE)))
                : jsonSchemaNodeType(stringValue(source.get(FIELD_TYPE)));
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put(FIELD_TYPE, type);
        String description = topLevel
                ? buildFieldDescription(source) : stringValue(source.get(FIELD_DESCRIPTION));
        if (StringUtils.isNotBlank(description)) {
            schema.put(FIELD_DESCRIPTION, description);
        }
        if ("array".equals(type)) {
            Map<String, Object> items = mapValue(source.get(FIELD_ITEMS));
            if (items.isEmpty()) {
                throw new IllegalArgumentException("array input items is required");
            }
            schema.put(FIELD_ITEMS, compileInputSchema(items, false));
        } else if ("object".equals(type)) {
            Map<String, Object> properties = mapValue(source.get(FIELD_PROPERTIES));
            Map<String, Object> compiledProperties = new LinkedHashMap<>();
            properties.forEach((name, propertySchema) -> {
                Map<String, Object> property = mapValue(propertySchema);
                if (StringUtils.isBlank(name) || property.isEmpty()) {
                    throw new IllegalArgumentException("object input property schema is invalid");
                }
                compiledProperties.put(name, compileInputSchema(property, false));
            });
            schema.put(FIELD_PROPERTIES, compiledProperties);
            schema.put(FIELD_REQUIRED, requiredPropertyNames(source.get(FIELD_REQUIRED), properties));
            schema.put(FIELD_ADDITIONAL_PROPERTIES, false);
        }
        return schema;
    }

    private List<String> requiredPropertyNames(Object value, Map<String, Object> properties) {
        if (value == null) {
            return Collections.emptyList();
        }
        if (!(value instanceof List)) {
            throw new IllegalArgumentException("object input required must be array");
        }
        List<String> result = new ArrayList<>();
        for (Object item : (List<?>) value) {
            String field = stringValue(item);
            if (StringUtils.isBlank(field) || !properties.containsKey(field)) {
                throw new IllegalArgumentException("object input required contains unknown property");
            }
            if (!result.contains(field)) {
                result.add(field);
            }
        }
        return result;
    }

    private String buildFieldDescription(Map<String, Object> field) {
        List<String> parts = new ArrayList<>();
        addDescriptionPart(parts, stringValue(field.get(FIELD_BUSINESS_MEANING)));
        addDescriptionPart(parts, StringUtils.isBlank(stringValue(field.get(FIELD_UNIT)))
                ? StringUtils.EMPTY : "单位：" + stringValue(field.get(FIELD_UNIT)));
        addDescriptionPart(parts, allowedValuesDescription(field));
        addDescriptionPart(parts, StringUtils.isBlank(stringValue(field.get(FIELD_EXAMPLES)))
                ? StringUtils.EMPTY : "示例：" + stringValue(field.get(FIELD_EXAMPLES)));
        return String.join("；", parts);
    }

    /** 编译模型可见枚举并再次校验发布快照，避免非法闭集进入运行时。 */
    private List<Object> compileAllowedValues(Map<String, Object> field, String fieldType) {
        Object value = field.get(FIELD_ALLOWED_VALUES);
        if (value == null) {
            return Collections.emptyList();
        }
        if (!StringUtils.equalsAny(fieldType, "string", "number", "integer")) {
            throw new IllegalArgumentException("allowedValues only supports string, number or integer input");
        }
        if (!(value instanceof List)) {
            throw new IllegalArgumentException("allowedValues must be an array");
        }
        List<Object> result = new ArrayList<>();
        Set<String> identities = new LinkedHashSet<>();
        for (Object itemValue : (List<?>) value) {
            Map<String, Object> item = mapValue(itemValue);
            Object allowedValue = item.get(FIELD_VALUE);
            if (StringUtils.isBlank(stringValue(item.get(FIELD_LABEL)))
                    || !matchesJsonType(allowedValue, fieldType)) {
                throw new IllegalArgumentException("allowedValues item is invalid");
            }
            String identity = allowedValueIdentity(allowedValue, fieldType);
            if (!identities.add(identity)) {
                throw new IllegalArgumentException("allowedValues item is duplicated");
            }
            result.add(allowedValue);
        }
        if (result.isEmpty()) {
            throw new IllegalArgumentException("allowedValues must not be empty");
        }
        return List.copyOf(result);
    }

    private String allowedValuesDescription(Map<String, Object> field) {
        Object value = field.get(FIELD_ALLOWED_VALUES);
        if (!(value instanceof List) || ((List<?>) value).isEmpty()) {
            return StringUtils.EMPTY;
        }
        return "可选值：" + ((List<?>) value).stream()
                .map(this::mapValue)
                .map(item -> stringValue(item.get(FIELD_VALUE)) + "（" + stringValue(item.get(FIELD_LABEL)) + "）")
                .collect(Collectors.joining("、"));
    }

    private boolean matchesJsonType(Object value, String fieldType) {
        return "string".equals(fieldType)
                ? value instanceof String && StringUtils.isNotBlank((String) value)
                : "integer".equals(fieldType) ? CapabilityIntegerSupport.isInteger(value)
                : "number".equals(fieldType) && value instanceof Number;
    }

    private String allowedValueIdentity(Object value, String fieldType) {
        if (StringUtils.equalsAny(fieldType, "number", "integer")) {
            return "number:" + new BigDecimal(String.valueOf(value)).stripTrailingZeros().toPlainString();
        }
        return "string:" + value;
    }

    private void addDescriptionPart(List<String> parts, String value) {
        if (StringUtils.isNotBlank(value)) {
            parts.add(value);
        }
    }

    /** 校验全部作者字段身份，保证执行映射不会遗留未知或重复字段。 */
    private List<String> inputFieldNames(List<Map<String, Object>> inputFields) {
        List<String> result = new ArrayList<>();
        for (Map<String, Object> field : inputFields) {
            String toolField = required(field, FIELD_TOOL_FIELD);
            if (result.contains(toolField)) {
                throw new IllegalArgumentException("capability input field is duplicated: " + toolField);
            }
            jsonSchemaType(stringValue(field.get(FIELD_TYPE)));
            String source = required(field, FIELD_FIELD_SOURCE);
            if (!StringUtils.equalsAny(source, FIELD_SOURCE_MODEL_INPUT, FIELD_SOURCE_CONSTANT,
                    FIELD_SOURCE_SYSTEM_VARIABLE)) {
                throw new IllegalArgumentException(
                        "capability input source must be MODEL_INPUT, CONSTANT or SYSTEM_VARIABLE");
            }
            result.add(toolField);
        }
        return result;
    }

    private Map<String, String> modelRequestMappings(List<String> modelArgumentFields,
            Map<String, String> allRequestMappings) {
        Map<String, String> result = new LinkedHashMap<>();
        for (String field : modelArgumentFields) {
            result.put(field, allRequestMappings.get(field));
        }
        return result;
    }

    /** 把常量字段名通过同一请求映射编译为执行器消费的 requestPath -> value。 */
    private Map<String, Object> compileConstantMappings(List<Map<String, Object>> inputFields,
            Map<String, String> allRequestMappings) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map<String, Object> field : inputFields) {
            if (!FIELD_SOURCE_CONSTANT.equals(stringValue(field.get(FIELD_FIELD_SOURCE)))) {
                continue;
            }
            String toolField = required(field, FIELD_TOOL_FIELD);
            Object value = field.get(FIELD_CONSTANT_VALUE);
            if (value == null || value instanceof String && StringUtils.isBlank((String) value)) {
                throw new IllegalArgumentException("constantValue is required for field: " + toolField);
            }
            result.put(allRequestMappings.get(toolField), typedConstantValue(field, value));
        }
        return result;
    }

    private Object typedConstantValue(Map<String, Object> field, Object value) {
        String type = stringValue(field.get(FIELD_TYPE));
        if ("integer".equals(type)) {
            return CapabilityIntegerSupport.normalize(value, Map.of(FIELD_TYPE, type));
        }
        if ("string".equals(type)) {
            if (!(value instanceof String)) {
                throw new IllegalArgumentException("constantValue must be string");
            }
            return value;
        }
        if ("boolean".equals(type)) {
            if (!(value instanceof Boolean)) {
                throw new IllegalArgumentException("constantValue must be boolean");
            }
            return value;
        }
        if ("array".equals(type)) {
            if (!(value instanceof List)) {
                throw new IllegalArgumentException("constantValue must be array");
            }
            Map<String, Object> schema = compileInputSchema(field, true);
            validateSchemaValue(value, schema, "constantValue");
            return CapabilityIntegerSupport.normalize(value, schema);
        }
        if (value instanceof Number) {
            return value;
        }
        try {
            return new BigDecimal(String.valueOf(value));
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException("constantValue must be number", exception);
        }
    }

    /** 编译系统变量值映射；未配置映射时执行器直接使用可信上下文原值。 */
    private Map<String, Map<String, String>> compileContextValueMappings(
            List<Map<String, Object>> inputFields, Map<String, String> allRequestMappings) {
        Map<String, Map<String, String>> result = new LinkedHashMap<>();
        for (Map<String, Object> field : inputFields) {
            if (!FIELD_SOURCE_SYSTEM_VARIABLE.equals(stringValue(field.get(FIELD_FIELD_SOURCE)))) {
                continue;
            }
            String systemVariable = required(field, FIELD_SYSTEM_VARIABLE);
            if (!StringUtils.equalsAny(systemVariable, SYSTEM_VARIABLE_USER_ID, SYSTEM_VARIABLE_CLIENT)) {
                throw new IllegalArgumentException("unsupported capability systemVariable: " + systemVariable);
            }
            String type = stringValue(field.get(FIELD_TYPE));
            if (SYSTEM_VARIABLE_USER_ID.equals(systemVariable) && !"string".equals(type)
                    || SYSTEM_VARIABLE_CLIENT.equals(systemVariable) && !"string".equals(type)) {
                throw new IllegalArgumentException("capability systemVariable type does not match: "
                        + systemVariable);
            }
            Map<String, String> valueMapping = stringObjectMap(field.get(FIELD_VALUE_MAPPING));
            if (SYSTEM_VARIABLE_USER_ID.equals(systemVariable) && !valueMapping.isEmpty()) {
                throw new IllegalArgumentException("userId systemVariable does not support valueMapping");
            }
            if (!valueMapping.isEmpty()) {
                result.put(allRequestMappings.get(required(field, FIELD_TOOL_FIELD)), valueMapping);
            }
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, String> stringObjectMap(Object value) {
        if (value == null) {
            return Collections.emptyMap();
        }
        if (!(value instanceof Map)) {
            throw new IllegalArgumentException("valueMapping must be an object");
        }
        Map<String, String> result = new LinkedHashMap<>();
        ((Map<String, Object>) value).forEach((key, item) -> {
            if (!(item instanceof String) || StringUtils.isBlank(key) || StringUtils.isBlank((String) item)) {
                throw new IllegalArgumentException("valueMapping must contain non-blank string pairs");
            }
            result.put(key, (String) item);
        });
        return result;
    }

    /**
     * 把发布快照中的关键出参说明投影为模型可见只读元数据，不携带响应 Demo 或技术 Schema。
     */
    private List<Map<String, Object>> immutableKeyOutputFields(Object value) {
        List<Map<String, Object>> fields = listOfMaps(value);
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> field : fields) {
            Map<String, Object> item = new LinkedHashMap<>();
            copyNonBlank(item, FIELD_PATH, field.get(FIELD_PATH));
            copyNonBlank(item, FIELD_DESCRIPTION, field.get(FIELD_DESCRIPTION));
            copyNonBlank(item, FIELD_OBSERVED_TYPE, field.get(FIELD_OBSERVED_TYPE));
            if (!item.isEmpty()) {
                result.add(Collections.unmodifiableMap(item));
            }
        }
        return Collections.unmodifiableList(result);
    }

    private void copyNonBlank(Map<String, Object> target, String field, Object value) {
        if (value != null && StringUtils.isNotBlank(String.valueOf(value))) {
            target.put(field, value);
        }
    }

    private String buildToolDescription(Map<String, Object> basicInfo, Map<String, Object> modelContract) {
        return StringUtils.defaultIfBlank(stringValue(modelContract.get(FIELD_DESCRIPTION)),
                stringValue(basicInfo.get(FIELD_DESCRIPTION)));
    }

    private void validateRequestMappings(List<String> inputFieldNames,
            Map<String, String> requestMappings) {
        for (String toolField : requestMappings.keySet()) {
            if (!inputFieldNames.contains(toolField)) {
                throw new IllegalArgumentException("requestMappingsJson contains unknown input field: "
                        + toolField);
            }
        }
        for (String toolField : inputFieldNames) {
            if (!requestMappings.containsKey(toolField)) {
                throw new IllegalArgumentException("requestMappingsJson is missing input field: " + toolField);
            }
        }
    }

    private void validateMappingTargets(Map<String, String> requestMappings,
            Map<String, String> contextMappings, Map<String, Object> constantMappings) {
        List<String> targetPaths = new ArrayList<>(requestMappings.values());
        targetPaths.addAll(contextMappings.keySet());
        targetPaths.addAll(constantMappings.keySet());
        for (int index = 0; index < targetPaths.size(); index++) {
            String current = targetPaths.get(index);
            if (StringUtils.isBlank(current)) {
                throw new IllegalArgumentException("request mapping target path is required");
            }
            for (int otherIndex = index + 1; otherIndex < targetPaths.size(); otherIndex++) {
                String other = targetPaths.get(otherIndex);
                if (StringUtils.equals(current, other) || current.startsWith(other + ".")
                        || other.startsWith(current + ".")) {
                    throw new IllegalArgumentException("request mapping target path conflicts: "
                            + current + " and " + other);
                }
            }
        }
    }

    private int timeoutMs(Object value) {
        return boundedPositiveInteger(value, DEFAULT_TIMEOUT_MS, MAX_TIMEOUT_MS, FIELD_TIMEOUT_MS);
    }

    private int maxResponseBytes(Object value) {
        return boundedPositiveInteger(value, DEFAULT_MAX_RESPONSE_BYTES, MAX_RESPONSE_BYTES,
                FIELD_MAX_RESPONSE_BYTES);
    }

    private int boundedPositiveInteger(Object value, int defaultValue, int maxValue, String fieldName) {
        if (value == null || StringUtils.isBlank(String.valueOf(value))) {
            return defaultValue;
        }
        try {
            int parsed = exactInteger(value);
            if (parsed <= 0 || parsed > maxValue) {
                throw new IllegalArgumentException(fieldName + " must be greater than 0 and at most " + maxValue);
            }
            return parsed;
        } catch (NumberFormatException | ArithmeticException exception) {
            throw new IllegalArgumentException(fieldName + " must be a positive integer", exception);
        }
    }

    private Set<Integer> successStatusCodes(Object value) {
        if (!(value instanceof List) || ((List<?>) value).isEmpty()) {
            return defaultSuccessStatusCodes();
        }
        Set<Integer> result = new java.util.LinkedHashSet<>();
        for (Object item : (List<?>) value) {
            if (StringUtils.equalsIgnoreCase(SUCCESS_STATUS_2XX, String.valueOf(item))) {
                result.addAll(defaultSuccessStatusCodes());
                continue;
            }
            try {
                int statusCode = exactInteger(item);
                if (statusCode < HTTP_STATUS_MIN || statusCode > HTTP_STATUS_MAX) {
                    throw new IllegalArgumentException("successStatusCodes contains invalid HTTP status");
                }
                result.add(statusCode);
            } catch (NumberFormatException | ArithmeticException exception) {
                throw new IllegalArgumentException("successStatusCodes must contain HTTP status or 2XX",
                        exception);
            }
        }
        return Collections.unmodifiableSet(result);
    }

    /** 数字输入必须能精确表示为 int；拒绝溢出和非整数，字符串沿用原整数语法。 */
    private int exactInteger(Object value) {
        return value instanceof Number
                ? new BigDecimal(value.toString()).intValueExact()
                : Integer.parseInt(String.valueOf(value));
    }

    private Set<Integer> defaultSuccessStatusCodes() {
        return IntStream.rangeClosed(HTTP_SUCCESS_STATUS_MIN, HTTP_SUCCESS_STATUS_MAX)
                .boxed()
                .collect(Collectors.toUnmodifiableSet());
    }

    private String jsonSchemaType(String type) {
        String normalized = StringUtils.lowerCase(type, Locale.ROOT);
        if (Set.of("string", "number", "integer", "boolean", "array").contains(normalized)) {
            return normalized;
        }
        throw new IllegalArgumentException(
                "capability input type must be string, number, integer, boolean or array: " + type);
    }

    private String jsonSchemaNodeType(String type) {
        String normalized = StringUtils.lowerCase(type, Locale.ROOT);
        if (Set.of("string", "number", "integer", "boolean", "array", "object").contains(normalized)) {
            return normalized;
        }
        throw new IllegalArgumentException("capability items type is invalid: " + type);
    }

    /** 编译常量时递归校验数组元素，防止非法不可变计划进入运行时。 */
    private void validateSchemaValue(Object value, Map<String, Object> schema, String path) {
        if (value == null) {
            return;
        }
        String type = stringValue(schema.get(FIELD_TYPE));
        boolean matched = "string".equals(type) ? value instanceof String
                : "number".equals(type) ? value instanceof Number
                : "integer".equals(type) ? CapabilityIntegerSupport.isInteger(value)
                : "boolean".equals(type) ? value instanceof Boolean
                : "array".equals(type) ? value instanceof List
                : "object".equals(type) && value instanceof Map;
        if (!matched) {
            throw new IllegalArgumentException(path + " does not match input schema type " + type);
        }
        if ("array".equals(type)) {
            Map<String, Object> items = mapValue(schema.get(FIELD_ITEMS));
            List<?> values = (List<?>) value;
            for (int index = 0; index < values.size(); index++) {
                validateSchemaValue(values.get(index), items, path + "[" + index + "]");
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
            for (Object field : (List<?>) requiredValue) {
                if (!objectValue.containsKey(field) || objectValue.get(field) == null) {
                    throw new IllegalArgumentException(path + "." + field + " is required");
                }
            }
        }
        for (Map.Entry<String, Object> entry : objectValue.entrySet()) {
            Map<String, Object> propertySchema = mapValue(properties.get(entry.getKey()));
            if (propertySchema.isEmpty()) {
                throw new IllegalArgumentException(path + " contains unknown property " + entry.getKey());
            }
            validateSchemaValue(entry.getValue(), propertySchema, path + "." + entry.getKey());
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    private List<Map<String, Object>> listOfMaps(Object value) {
        if (!(value instanceof List)) {
            return Collections.emptyList();
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : (List<?>) value) {
            Map<String, Object> map = mapValue(item);
            if (!map.isEmpty()) {
                result.add(map);
            }
        }
        return result;
    }

    private Map<String, String> stringMap(Object jsonValue, String fieldName) {
        Map<String, Object> source = objectMap(jsonValue, fieldName);
        Map<String, String> result = new LinkedHashMap<>();
        source.forEach((key, value) -> result.put(key, value == null ? StringUtils.EMPTY : String.valueOf(value)));
        return result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> objectMap(Object jsonValue, String fieldName) {
        String json = stringValue(jsonValue);
        if (StringUtils.isBlank(json)) {
            return Collections.emptyMap();
        }
        try {
            Object value = JsonSupport.fromJSON(json, Object.class);
            if (!(value instanceof Map)) {
                throw new IllegalArgumentException(fieldName + " must be a JSON object");
            }
            return new LinkedHashMap<>((Map<String, Object>) value);
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException(fieldName + " must be valid JSON", e);
        }
    }

    private String required(Map<String, Object> source, String field) {
        String value = stringValue(source.get(field));
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value.trim();
    }

    private String stringValue(Object value) {
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }

    private <K, V> Map<K, V> unmodifiableMap(Map<K, V> source) {
        return Collections.unmodifiableMap(new LinkedHashMap<>(source));
    }

    private Map<String, List<Object>> unmodifiableListMap(Map<String, List<Object>> source) {
        Map<String, List<Object>> result = new LinkedHashMap<>();
        source.forEach((key, value) -> result.put(key, List.copyOf(value)));
        return Collections.unmodifiableMap(result);
    }

    private Map<String, Object> unmodifiableObjectMap(Map<String, Object> source) {
        return Collections.unmodifiableMap(new LinkedHashMap<>(source));
    }

    private Map<String, Map<String, Object>> unmodifiableSchemaMap(
            Map<String, Map<String, Object>> source) {
        Map<String, Map<String, Object>> result = new LinkedHashMap<>();
        source.forEach((key, value) -> result.put(key, unmodifiableObjectMap(value)));
        return Collections.unmodifiableMap(result);
    }

    private Map<String, Map<String, String>> unmodifiableNestedMap(
            Map<String, Map<String, String>> source) {
        Map<String, Map<String, String>> result = new LinkedHashMap<>();
        source.forEach((key, value) -> result.put(key, unmodifiableMap(value)));
        return Collections.unmodifiableMap(result);
    }
}
