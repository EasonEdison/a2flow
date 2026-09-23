package dev.a2flow.management.lifecycle;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.support.JsonSupport;

/**
 * 能力草稿执行绑定规范化器。
 *
 * <p>只保留 GRPC 注册字段与确定性参数映射。HTTP/本地方法不自动迁移或降级。
 * 不读取环境地址、凭据，也不执行外部调用。
 */
final class CapabilityActionExecutionBindingCanonicalizer {

    private static final String FIELD_BINDING_TYPE = "bindingType";
    private static final String FIELD_TARGET = "target";
    private static final String FIELD_REQUEST_MAPPINGS_JSON = "requestMappingsJson";
    private static final String FIELD_CONTEXT_MAPPINGS_JSON = "contextMappingsJson";
    private static final String FIELD_TIMEOUT_MS = "timeoutMs";
    private static final String FIELD_MAX_RESPONSE_BYTES = "maxResponseBytes";
    private static final String FIELD_RESPONSE_POLICY = "responsePolicy";
    private static final String FIELD_IDEMPOTENCY = "idempotency";
    private static final String FIELD_INPUT_FIELDS = "inputFields";
    private static final String FIELD_TOOL_FIELD = "toolField";
    private static final String FIELD_FIELD_SOURCE = "source";
    private static final String FIELD_SYSTEM_VARIABLE = "systemVariable";
    private static final String FIELD_SOURCE_SYSTEM_VARIABLE = "SYSTEM_VARIABLE";
    private static final int DEFAULT_HTTP_TIMEOUT_MS = 3000;
    private static final int DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024;
    private static final String IDEMPOTENCY_NONE = "NONE";
    private static final String RESPONSE_POLICY_ORIGINAL = "ORIGINAL";

    private CapabilityActionExecutionBindingCanonicalizer() {
    }

    /**
     * 重建执行绑定系统字段，并保留研发已批准的当前字段目标路径。
     */
    static Map<String, Object> canonicalize(Map<String, Object> source,
            Map<String, Object> modelContract, String sourceType) {
        if (!"GRPC".equals(sourceType) || !"GRPC".equals(source.get(FIELD_BINDING_TYPE))) {
            throw new IllegalArgumentException("Only GRPC capability bindings are supported; no HTTP fallback");
        }
        java.util.Set<String> allowed = java.util.Set.of("bindingType", "target", "timeoutMs", "maxResponseBytes",
                "idempotency", "responsePolicy", "requestMappingsJson", "contextMappingsJson");
        if (!allowed.containsAll(source.keySet())) throw new IllegalArgumentException("HTTP/unknown binding fields forbidden");
        Map<String, Object> result = new LinkedHashMap<>(source);
        Map<String, Object> target = new LinkedHashMap<>(mapValue(source.get(FIELD_TARGET)));
        if (!java.util.Set.of("targetKey", "serviceName", "methodName", "descriptorSetBase64", "contextField")
                .containsAll(target.keySet())) throw new IllegalArgumentException("HTTP/unknown target fields forbidden");
        result.put(FIELD_TARGET, target);
        result.putIfAbsent(FIELD_TIMEOUT_MS, DEFAULT_HTTP_TIMEOUT_MS);
        result.putIfAbsent(FIELD_MAX_RESPONSE_BYTES, DEFAULT_MAX_RESPONSE_BYTES);
        result.putIfAbsent(FIELD_IDEMPOTENCY, IDEMPOTENCY_NONE);
        result.putIfAbsent(FIELD_RESPONSE_POLICY, RESPONSE_POLICY_ORIGINAL);
        Map<String, String> mappings = canonicalRequestMappings(source.get(FIELD_REQUEST_MAPPINGS_JSON), modelContract.get(FIELD_INPUT_FIELDS));
        result.put(FIELD_REQUEST_MAPPINGS_JSON, JsonSupport.toJSON(mappings));
        result.put(FIELD_CONTEXT_MAPPINGS_JSON, JsonSupport.toJSON(canonicalContextMappings(modelContract.get(FIELD_INPUT_FIELDS), mappings)));
        return result;
    }

    private static Map<String, String> canonicalRequestMappings(Object currentMappings, Object inputFieldsValue) {
        if (!(inputFieldsValue instanceof List)) {
            return Collections.emptyMap();
        }
        Map<String, String> current = parseStringMap(currentMappings);
        Map<String, String> mappings = new LinkedHashMap<>();
        for (Object item : (List<?>) inputFieldsValue) {
            Map<String, Object> inputField = mapValue(item);
            String toolField = StringUtils.trim(stringValue(inputField.get(FIELD_TOOL_FIELD)));
            if (StringUtils.isNotBlank(toolField)) {
                mappings.put(toolField, StringUtils.defaultIfBlank(current.get(toolField), toolField));
            }
        }
        return mappings;
    }

    /** 系统变量只能从当前输入字段协议生成，不能通过高级 JSON 注入未批准上下文。 */
    private static Map<String, String> canonicalContextMappings(Object inputFieldsValue,
            Map<String, String> requestMappings) {
        if (!(inputFieldsValue instanceof List)) {
            return Collections.emptyMap();
        }
        Map<String, String> mappings = new LinkedHashMap<>();
        for (Object item : (List<?>) inputFieldsValue) {
            Map<String, Object> inputField = mapValue(item);
            if (!FIELD_SOURCE_SYSTEM_VARIABLE.equals(stringValue(inputField.get(FIELD_FIELD_SOURCE)))) {
                continue;
            }
            String toolField = StringUtils.trim(stringValue(inputField.get(FIELD_TOOL_FIELD)));
            String systemVariable = StringUtils.trim(stringValue(inputField.get(FIELD_SYSTEM_VARIABLE)));
            String requestPath = requestMappings.get(toolField);
            if (StringUtils.isNotBlank(requestPath) && StringUtils.isNotBlank(systemVariable)) {
                mappings.put(requestPath, systemVariable);
            }
        }
        return mappings;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, String> parseStringMap(Object jsonValue) {
        String json = stringValue(jsonValue);
        if (StringUtils.isBlank(json)) {
            return Collections.emptyMap();
        }
        try {
            Object parsed = JsonSupport.fromJSON(json, Object.class);
            if (!(parsed instanceof Map)) {
                throw new IllegalArgumentException("requestMappingsJson must be a JSON object");
            }
            Map<String, String> result = new LinkedHashMap<>();
            ((Map<String, Object>) parsed).forEach((key, value) -> {
                if (value instanceof String && StringUtils.isNotBlank((String) value)) {
                    result.put(key, (String) value);
                }
            });
            return result;
        } catch (Exception exception) {
            throw new IllegalArgumentException("requestMappingsJson must be a valid JSON object", exception);
        }
    }

    /** 从无凭证、无查询参数的登记 URL 中提取固定 Path。 */
    @SuppressWarnings("unchecked")
    private static Map<String, Object> mapValue(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    private static String stringValue(Object value) {
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }
}
