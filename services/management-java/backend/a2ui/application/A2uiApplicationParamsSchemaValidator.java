package dev.a2flow.management.a2ui.application;

import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.PARAMS_SCHEMA_INVALID;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.PARAMS_SCHEMA_UNSUPPORTED;

import java.math.BigDecimal;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Application 参数 Schema 的发布兼容性门禁，与 Adviser A2uiJsonSchemaSubsetValidator 保持同一子集。
 *
 * <p>上游 Build compiler 提供 showTemplate.paramsSchema；本类只验证 Schema 结构，不生成参数样例、
 * 不调用业务能力、不读取数据库。Catalog 组件的完整协议不属于这一参数子集，不能经过本门禁。
 * 未支持或非法规则明确阻止新 Build，避免发布后到 Show 参数校验时才失败；不忽略未知关键字。
 */
public final class A2uiApplicationParamsSchemaValidator {
    private static final String TYPE = "type";
    private static final String OBJECT = "object";
    private static final String ARRAY = "array";
    private static final String STRING = "string";
    private static final String NUMBER = "number";
    private static final String INTEGER = "integer";
    private static final String PROPERTIES = "properties";
    private static final String REQUIRED = "required";
    private static final String ADDITIONAL_PROPERTIES = "additionalProperties";
    private static final String ITEMS = "items";
    private static final String ENUM = "enum";
    private static final String ANY_OF = "anyOf";
    private static final String MINIMUM = "minimum";
    private static final String MAXIMUM = "maximum";
    private static final String MIN_LENGTH = "minLength";
    private static final String MIN_ITEMS = "minItems";
    private static final String MAX_ITEMS = "maxItems";
    private static final String UNIQUE_ITEMS = "uniqueItems";
    private static final int MAX_DEPTH = 64;
    private static final int MAX_VISITED_SCHEMAS = 10_000;
    private static final Set<String> TYPES = Set.of(OBJECT, ARRAY, STRING, NUMBER, INTEGER, "boolean", "null");
    private static final Set<String> ANNOTATIONS = Set.of("$schema", "$id", "title", "description", "default",
            "examples", "deprecated", "readOnly", "writeOnly");
    private static final Set<String> RULES = Set.of(TYPE, PROPERTIES, REQUIRED, ADDITIONAL_PROPERTIES,
            ITEMS, ENUM, ANY_OF, MINIMUM, MAXIMUM, MIN_LENGTH, MIN_ITEMS, MAX_ITEMS, UNIQUE_ITEMS);

    /** 在 Build 编译产生身份及不可变产物之前，严格验证全部参数 Schema 分支。 */
    public void validate(Map<String, Object> schema) {
        require(schema != null && !schema.isEmpty());
        validateSchema(schema, 0, new Counter());
    }

    /** 仅沿 Schema 结构递归；default/examples 等注解中的业务 JSON 不应被当成 Schema。 */
    private void validateSchema(Map<String, Object> schema, int depth, Counter counter) {
        require(depth <= MAX_DEPTH && ++counter.visited <= MAX_VISITED_SCHEMAS);
        for (String key : schema.keySet()) {
            if (!RULES.contains(key) && !ANNOTATIONS.contains(key)) {
                throw new A2uiApplicationValidationException(PARAMS_SCHEMA_UNSUPPORTED);
            }
        }
        if (schema.containsKey(ANY_OF)) {
            for (String key : schema.keySet()) {
                require(ANY_OF.equals(key) || ANNOTATIONS.contains(key));
            }
            List<?> alternatives = list(schema.get(ANY_OF));
            require(!alternatives.isEmpty());
            for (Object alternative : alternatives) {
                validateSchema(map(alternative), depth + 1, counter);
            }
            return;
        }
        Object rawType = schema.get(TYPE);
        require(rawType instanceof String && !((String) rawType).isEmpty());
        String type = (String) rawType;
        if (!TYPES.contains(type)) {
            throw new A2uiApplicationValidationException(PARAMS_SCHEMA_UNSUPPORTED);
        }
        if (schema.containsKey(ENUM)) {
            require(!list(schema.get(ENUM)).isEmpty());
        }
        validateBounds(schema, type);
        if (OBJECT.equals(type)) {
            Map<String, Object> properties = schema.get(PROPERTIES) == null
                    ? Collections.emptyMap() : map(schema.get(PROPERTIES));
            for (Object property : properties.values()) {
                validateSchema(map(property), depth + 1, counter);
            }
            for (Object field : list(schema.get(REQUIRED))) {
                require(field instanceof String && !((String) field).isEmpty());
            }
            Object additional = schema.get(ADDITIONAL_PROPERTIES);
            require(additional == null || additional instanceof Boolean || additional instanceof Map);
            if (additional instanceof Map) {
                validateSchema(map(additional), depth + 1, counter);
            }
            require(!schema.containsKey(ITEMS));
        } else if (ARRAY.equals(type)) {
            validateSchema(map(schema.get(ITEMS)), depth + 1, counter);
            rejectObjectKeywords(schema);
        } else {
            rejectObjectKeywords(schema);
            require(!schema.containsKey(ITEMS));
        }
    }

    /** 与运行时一致地检查数值、字符串、数组约束的类型和边界，不进行类型强转容错。 */
    private void validateBounds(Map<String, Object> schema, String type) {
        if (schema.containsKey(MINIMUM) || schema.containsKey(MAXIMUM)) {
            require(NUMBER.equals(type) || INTEGER.equals(type));
            requireOrdered(bound(schema, MINIMUM, false), bound(schema, MAXIMUM, false));
        }
        if (schema.containsKey(MIN_LENGTH)) {
            require(STRING.equals(type));
            bound(schema, MIN_LENGTH, true);
        }
        if (schema.containsKey(MIN_ITEMS) || schema.containsKey(MAX_ITEMS) || schema.containsKey(UNIQUE_ITEMS)) {
            require(ARRAY.equals(type));
            requireOrdered(bound(schema, MIN_ITEMS, true), bound(schema, MAX_ITEMS, true));
            require(!schema.containsKey(UNIQUE_ITEMS) || schema.get(UNIQUE_ITEMS) instanceof Boolean);
        }
    }

    /** 有限数值按 BigDecimal 校验，保留大整数精度并拒绝负数/小数长度。 */
    private BigDecimal bound(Map<String, Object> schema, String key, boolean length) {
        if (!schema.containsKey(key)) {
            return null;
        }
        Object value = schema.get(key);
        require(value instanceof Number);
        BigDecimal number;
        try {
            number = new BigDecimal(String.valueOf(value));
        } catch (NumberFormatException exception) {
            throw new A2uiApplicationValidationException(PARAMS_SCHEMA_INVALID);
        }
        require(!length || number.signum() >= 0 && number.stripTrailingZeros().scale() <= 0);
        return number;
    }

    private void requireOrdered(BigDecimal minimum, BigDecimal maximum) {
        require(minimum == null || maximum == null || minimum.compareTo(maximum) <= 0);
    }

    private void rejectObjectKeywords(Map<String, Object> schema) {
        require(!schema.containsKey(PROPERTIES) && !schema.containsKey(REQUIRED)
                && !schema.containsKey(ADDITIONAL_PROPERTIES));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value) {
        require(value instanceof Map);
        return (Map<String, Object>) value;
    }

    private List<?> list(Object value) {
        if (value == null) {
            return Collections.emptyList();
        }
        require(value instanceof List);
        return (List<?>) value;
    }

    /** 稳定领域错误不携带原始 Schema、参数或凭证，沿用既有发布失败响应。 */
    private void require(boolean valid) {
        if (!valid) {
            throw new A2uiApplicationValidationException(PARAMS_SCHEMA_INVALID);
        }
    }

    private static final class Counter {
        private int visited;
    }
}
