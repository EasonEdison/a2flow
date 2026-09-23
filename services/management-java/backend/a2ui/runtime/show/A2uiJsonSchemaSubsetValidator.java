package dev.a2flow.management.a2ui.runtime.show;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * A2UI Application Tool 参数的有界 JSON Schema 校验器。
 *
 * <p>上游传入不可变 Application Build 中的 {@code paramsSchema} 与模型产生的 {@code params}；
 * 本类在任何 LoadBinding 或业务能力调用前校验值类型、必填字段、对象边界、数组元素与枚举。
 * 首版没有引入新的 Schema 运行库，因此只接受本类显式声明的关键字；组合 Schema 仅支持无兄弟校验
 * 关键字的 {@code anyOf}，遇到引用或其他未实现关键字时失败关闭，不会静默忽略，也不负责
 * ShowTemplate 绑定、Capability 执行或 SSE。</p>
 */
public class A2uiJsonSchemaSubsetValidator {

    private static final String ROOT_PATH = "$";
    private static final String TYPE_OBJECT = "object";
    private static final String TYPE_ARRAY = "array";
    private static final String TYPE_STRING = "string";
    private static final String TYPE_NUMBER = "number";
    private static final String TYPE_INTEGER = "integer";
    private static final String TYPE_BOOLEAN = "boolean";
    private static final String TYPE_NULL = "null";
    private static final String KEY_TYPE = "type";
    private static final String KEY_PROPERTIES = "properties";
    private static final String KEY_REQUIRED = "required";
    private static final String KEY_ITEMS = "items";
    private static final String KEY_ADDITIONAL_PROPERTIES = "additionalProperties";
    private static final String KEY_ENUM = "enum";
    private static final String KEY_MINIMUM = "minimum";
    private static final String KEY_MAXIMUM = "maximum";
    private static final String KEY_MIN_LENGTH = "minLength";
    private static final String KEY_MIN_ITEMS = "minItems";
    private static final String KEY_MAX_ITEMS = "maxItems";
    private static final String KEY_UNIQUE_ITEMS = "uniqueItems";
    private static final String KEY_ANY_OF = "anyOf";
    private static final int MAX_DEPTH = 64;
    private static final int MAX_VISITED_VALUES = 10_000;

    private static final Set<String> SUPPORTED_TYPES = Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
            TYPE_OBJECT, TYPE_ARRAY, TYPE_STRING, TYPE_NUMBER, TYPE_INTEGER, TYPE_BOOLEAN, TYPE_NULL)));
    private static final Set<String> SUPPORTED_KEYWORDS = Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
            "$schema", "$id", "title", "description", "default", "examples", "deprecated",
            "readOnly", "writeOnly", KEY_TYPE, KEY_PROPERTIES, KEY_REQUIRED, KEY_ITEMS,
            KEY_ADDITIONAL_PROPERTIES, KEY_ENUM, KEY_MINIMUM, KEY_MAXIMUM, KEY_MIN_LENGTH,
            KEY_MIN_ITEMS, KEY_MAX_ITEMS, KEY_UNIQUE_ITEMS, KEY_ANY_OF)));
    private static final Set<String> ANNOTATION_KEYWORDS = Collections.unmodifiableSet(
            new HashSet<>(Arrays.asList("$schema", "$id", "title", "description", "default",
                    "examples", "deprecated", "readOnly", "writeOnly")));

    /**
     * 校验一个 JSON 值；Schema 本身不完整、出现未支持关键字或实例不匹配时均抛出稳定异常。
     */
    public void validate(Map<String, Object> schema, Object value) {
        if (schema == null || schema.isEmpty()) {
            throw failure(Code.SCHEMA_INVALID, ROOT_PATH, "schema is required");
        }
        validateSchemaStructure(schema, ROOT_PATH, 0, new Counter());
        validateValue(schema, value, ROOT_PATH, 0, new Counter());
    }

    private void validateSchemaStructure(Map<String, Object> schema,
            String path, int depth, Counter counter) {
        if (depth > MAX_DEPTH || ++counter.visitedValues > MAX_VISITED_VALUES) {
            throw failure(Code.SCHEMA_INVALID, path, "schema exceeds validation limit");
        }
        validateSchemaKeywords(schema, path);
        if (schema.containsKey(KEY_ANY_OF)) {
            validateAnyOfSchema(schema, path, depth, counter);
            return;
        }
        String expectedType = requiredString(schema.get(KEY_TYPE), path, KEY_TYPE);
        if (!SUPPORTED_TYPES.contains(expectedType)) {
            throw failure(Code.SCHEMA_UNSUPPORTED, path, "unsupported schema type");
        }
        if (schema.containsKey(KEY_ENUM)
                && optionalList(schema.get(KEY_ENUM), path, KEY_ENUM).isEmpty()) {
            throw failure(Code.SCHEMA_INVALID, path, "enum must not be empty");
        }
        validateNumericBoundsSchema(schema, expectedType, path);
        if (schema.containsKey(KEY_MIN_LENGTH)) {
            if (!TYPE_STRING.equals(expectedType)) {
                throw failure(Code.SCHEMA_INVALID, path,
                        "minLength requires string type");
            }
            BigDecimal minLength = decimal(
                    schema.get(KEY_MIN_LENGTH), path, KEY_MIN_LENGTH, Code.SCHEMA_INVALID);
            if (minLength.signum() < 0 || minLength.stripTrailingZeros().scale() > 0) {
                throw failure(Code.SCHEMA_INVALID, path,
                        "minLength must be a non-negative integer");
            }
        }
        validateArrayConstraintsSchema(schema, expectedType, path);
        if (TYPE_OBJECT.equals(expectedType)) {
            Map<String, Object> properties = optionalMap(
                    schema.get(KEY_PROPERTIES), path, KEY_PROPERTIES);
            for (Map.Entry<String, Object> property : properties.entrySet()) {
                String childPath = childPath(path, property.getKey());
                validateSchemaStructure(requiredMap(
                        property.getValue(), childPath, KEY_PROPERTIES),
                        childPath, depth + 1, counter);
            }
            for (Object requiredField : optionalList(schema.get(KEY_REQUIRED), path, KEY_REQUIRED)) {
                if (!(requiredField instanceof String) || ((String) requiredField).isEmpty()) {
                    throw failure(Code.SCHEMA_INVALID, path,
                            "required entries must be non-empty strings");
                }
            }
            Object additionalProperties = schema.get(KEY_ADDITIONAL_PROPERTIES);
            if (additionalProperties != null && !(additionalProperties instanceof Boolean)
                    && !(additionalProperties instanceof Map)) {
                throw failure(Code.SCHEMA_INVALID, path,
                        "additionalProperties must be boolean or schema");
            }
            if (additionalProperties instanceof Map) {
                validateSchemaStructure(requiredMap(additionalProperties,
                                path, KEY_ADDITIONAL_PROPERTIES),
                        path + ".*", depth + 1, counter);
            }
            if (schema.containsKey(KEY_ITEMS)) {
                throw failure(Code.SCHEMA_INVALID, path,
                        "object schema cannot declare items");
            }
            return;
        }
        if (TYPE_ARRAY.equals(expectedType)) {
            validateSchemaStructure(requiredMap(schema.get(KEY_ITEMS), path, KEY_ITEMS),
                    path + "[]", depth + 1, counter);
            if (schema.containsKey(KEY_PROPERTIES) || schema.containsKey(KEY_REQUIRED)
                    || schema.containsKey(KEY_ADDITIONAL_PROPERTIES)) {
                throw failure(Code.SCHEMA_INVALID, path,
                        "array schema cannot declare object keywords");
            }
            return;
        }
        rejectShapeKeywordsOnScalar(schema, path);
    }

    private void validateValue(Map<String, Object> schema, Object value,
            String path, int depth, Counter counter) {
        if (depth > MAX_DEPTH || ++counter.visitedValues > MAX_VISITED_VALUES) {
            throw failure(Code.VALUE_INVALID, path, "value exceeds validation limit");
        }
        if (schema.containsKey(KEY_ANY_OF)) {
            validateAnyOfValue(schema, value, path, depth, counter);
            return;
        }
        String expectedType = requiredString(schema.get(KEY_TYPE), path, KEY_TYPE);
        if (!matchesType(expectedType, value)) {
            throw failure(Code.VALUE_INVALID, path, "value type does not match schema");
        }
        validateEnum(schema, value, path);
        validateNumericBounds(schema, value, path);
        if (schema.containsKey(KEY_MIN_LENGTH)) {
            BigDecimal minLength = decimal(
                    schema.get(KEY_MIN_LENGTH), path, KEY_MIN_LENGTH, Code.SCHEMA_INVALID);
            String text = (String) value;
            int codePointLength = text.codePointCount(0, text.length());
            if (BigDecimal.valueOf(codePointLength).compareTo(minLength) < 0) {
                throw failure(Code.VALUE_INVALID, path,
                        "string length is less than minLength");
            }
        }
        if (TYPE_OBJECT.equals(expectedType)) {
            validateObject(schema, castMap(value, path), path, depth, counter);
        } else if (TYPE_ARRAY.equals(expectedType)) {
            validateArray(schema, (List<?>) value, path, depth, counter);
        } else {
            rejectShapeKeywordsOnScalar(schema, path);
        }
    }

    private void validateObject(Map<String, Object> schema, Map<String, Object> value,
            String path, int depth, Counter counter) {
        Map<String, Object> properties = optionalMap(schema.get(KEY_PROPERTIES), path, KEY_PROPERTIES);
        List<?> required = optionalList(schema.get(KEY_REQUIRED), path, KEY_REQUIRED);
        for (Object requiredField : required) {
            if (!(requiredField instanceof String) || !value.containsKey(requiredField)
                    || value.get(requiredField) == null) {
                throw failure(Code.VALUE_INVALID, childPath(path, String.valueOf(requiredField)),
                        "required property is missing", Reason.REQUIRED_PROPERTY_MISSING);
            }
        }
        Object additionalProperties = schema.get(KEY_ADDITIONAL_PROPERTIES);
        if (additionalProperties != null && !(additionalProperties instanceof Boolean)
                && !(additionalProperties instanceof Map)) {
            throw failure(Code.SCHEMA_INVALID, path, "additionalProperties must be boolean or schema");
        }
        for (Map.Entry<String, Object> entry : value.entrySet()) {
            String childPath = childPath(path, entry.getKey());
            Object rawPropertySchema = properties.get(entry.getKey());
            if (rawPropertySchema != null) {
                validateValue(requiredMap(rawPropertySchema, childPath, KEY_PROPERTIES),
                        entry.getValue(), childPath, depth + 1, counter);
            } else if (Boolean.FALSE.equals(additionalProperties)) {
                throw failure(Code.VALUE_INVALID, childPath, "additional property is not allowed");
            } else if (additionalProperties instanceof Map) {
                validateValue(requiredMap(additionalProperties, childPath, KEY_ADDITIONAL_PROPERTIES),
                        entry.getValue(), childPath, depth + 1, counter);
            }
        }
        if (schema.containsKey(KEY_ITEMS)) {
            throw failure(Code.SCHEMA_INVALID, path, "object schema cannot declare items");
        }
    }

    private void validateArray(Map<String, Object> schema, List<?> value,
            String path, int depth, Counter counter) {
        if (schema.containsKey(KEY_MIN_ITEMS)) {
            BigDecimal minItems = decimal(
                    schema.get(KEY_MIN_ITEMS), path, KEY_MIN_ITEMS, Code.SCHEMA_INVALID);
            if (BigDecimal.valueOf(value.size()).compareTo(minItems) < 0) {
                throw failure(Code.VALUE_INVALID, path,
                        "array size is less than minItems");
            }
        }
        if (schema.containsKey(KEY_MAX_ITEMS)) {
            BigDecimal maxItems = decimal(
                    schema.get(KEY_MAX_ITEMS), path, KEY_MAX_ITEMS, Code.SCHEMA_INVALID);
            if (BigDecimal.valueOf(value.size()).compareTo(maxItems) > 0) {
                throw failure(Code.VALUE_INVALID, path, "array size exceeds maxItems");
            }
        }
        Map<String, Object> itemSchema = requiredMap(schema.get(KEY_ITEMS), path, KEY_ITEMS);
        Set<Object> uniqueValues = Boolean.TRUE.equals(schema.get(KEY_UNIQUE_ITEMS)) ? new HashSet<>() : null;
        Counter uniqueCounter = new Counter();
        for (int index = 0; index < value.size(); index++) {
            String itemPath = path + "[" + index + "]";
            validateValue(itemSchema, value.get(index), itemPath, depth + 1, counter);
            if (uniqueValues != null && !uniqueValues.add(
                    uniqueValue(value.get(index), itemPath, depth + 1, uniqueCounter))) {
                throw failure(Code.VALUE_INVALID, itemPath, "array items must be unique");
            }
        }
        if (schema.containsKey(KEY_PROPERTIES) || schema.containsKey(KEY_REQUIRED)
                || schema.containsKey(KEY_ADDITIONAL_PROPERTIES)) {
            throw failure(Code.SCHEMA_INVALID, path, "array schema cannot declare object keywords");
        }
    }

    private void rejectShapeKeywordsOnScalar(Map<String, Object> schema, String path) {
        if (schema.containsKey(KEY_PROPERTIES) || schema.containsKey(KEY_REQUIRED)
                || schema.containsKey(KEY_ITEMS) || schema.containsKey(KEY_ADDITIONAL_PROPERTIES)) {
            throw failure(Code.SCHEMA_INVALID, path, "scalar schema cannot declare container keywords");
        }
    }

    private void validateSchemaKeywords(Map<String, Object> schema, String path) {
        for (String keyword : schema.keySet()) {
            if (!SUPPORTED_KEYWORDS.contains(keyword)) {
                throw failure(Code.SCHEMA_UNSUPPORTED, path, "unsupported schema keyword: " + keyword);
            }
        }
    }

    /** anyOf 只承担候选类型并集，不允许同时声明其他兄弟校验语义。 */
    private void validateAnyOfSchema(Map<String, Object> schema,
            String path, int depth, Counter counter) {
        for (String keyword : schema.keySet()) {
            if (!KEY_ANY_OF.equals(keyword) && !ANNOTATION_KEYWORDS.contains(keyword)) {
                throw failure(Code.SCHEMA_INVALID, path,
                        "anyOf cannot declare sibling validation keywords");
            }
        }
        List<?> alternatives = optionalList(schema.get(KEY_ANY_OF), path, KEY_ANY_OF);
        if (alternatives.isEmpty()) {
            throw failure(Code.SCHEMA_INVALID, path, "anyOf must not be empty");
        }
        for (int index = 0; index < alternatives.size(); index++) {
            String alternativePath = path + ".anyOf[" + index + "]";
            validateSchemaStructure(requiredMap(
                            alternatives.get(index), alternativePath, KEY_ANY_OF),
                    alternativePath, depth + 1, counter);
        }
    }

    /** 值命中任一已完成结构校验的候选 Schema 即通过。 */
    private void validateAnyOfValue(Map<String, Object> schema, Object value,
            String path, int depth, Counter counter) {
        List<?> alternatives = optionalList(schema.get(KEY_ANY_OF), path, KEY_ANY_OF);
        for (int index = 0; index < alternatives.size(); index++) {
            String alternativePath = path + ".anyOf[" + index + "]";
            try {
                validateValue(requiredMap(alternatives.get(index), alternativePath, KEY_ANY_OF),
                        value, path, depth + 1, counter);
                return;
            } catch (ValidationException exception) {
                if (exception.getCode() != Code.VALUE_INVALID) {
                    throw exception;
                }
            }
        }
        throw failure(Code.VALUE_INVALID, path, "value does not match anyOf");
    }

    /** 数组上下界必须是有序的非负整数；唯一性规则必须为布尔值，不能只接受关键字而不执行。 */
    private void validateArrayConstraintsSchema(Map<String, Object> schema,
            String expectedType, String path) {
        if (!schema.containsKey(KEY_MIN_ITEMS) && !schema.containsKey(KEY_MAX_ITEMS)
                && !schema.containsKey(KEY_UNIQUE_ITEMS)) {
            return;
        }
        if (!TYPE_ARRAY.equals(expectedType)) {
            throw failure(Code.SCHEMA_INVALID, path, "array constraints require array type");
        }
        BigDecimal minItems = arraySizeBound(schema, KEY_MIN_ITEMS, path);
        BigDecimal maxItems = arraySizeBound(schema, KEY_MAX_ITEMS, path);
        if (minItems != null && maxItems != null && minItems.compareTo(maxItems) > 0) {
            throw failure(Code.SCHEMA_INVALID, path, "minItems must not exceed maxItems");
        }
        if (schema.containsKey(KEY_UNIQUE_ITEMS) && !(schema.get(KEY_UNIQUE_ITEMS) instanceof Boolean)) {
            throw failure(Code.SCHEMA_INVALID, path, "uniqueItems must be boolean");
        }
    }

    /** 复用有限数值解析，避免整数溢出或把小数、字符串当作数组长度。 */
    private BigDecimal arraySizeBound(Map<String, Object> schema, String keyword, String path) {
        BigDecimal bound = optionalDecimal(schema, keyword, path, Code.SCHEMA_INVALID);
        if (bound != null && (bound.signum() < 0 || bound.stripTrailingZeros().scale() > 0)) {
            throw failure(Code.SCHEMA_INVALID, path,
                    keyword + " must be a non-negative integer");
        }
        return bound;
    }

    /**
     * 将数组元素转换为可哈希的 JSON 等价值，数值忽略 Java 类型和小数尾零，对象忽略键顺序。
     * 仅生成局部比较值，不改写业务参数；额外有界遍历覆盖未声明的对象属性，避免深层值绕过限额。
     */
    private Object uniqueValue(Object value, String path, int depth, Counter counter) {
        if (depth > MAX_DEPTH || ++counter.visitedValues > MAX_VISITED_VALUES) {
            throw failure(Code.VALUE_INVALID, path, "value exceeds validation limit");
        }
        if (value instanceof Number) {
            return decimal(value, path, KEY_UNIQUE_ITEMS, Code.VALUE_INVALID).stripTrailingZeros();
        }
        if (value instanceof List) {
            List<?> source = (List<?>) value;
            List<Object> normalized = new ArrayList<>();
            for (int index = 0; index < source.size(); index++) {
                normalized.add(uniqueValue(source.get(index), path + "[" + index + "]", depth + 1, counter));
            }
            return normalized;
        }
        if (value instanceof Map) {
            Map<String, Object> normalized = new HashMap<>();
            for (Map.Entry<String, Object> entry : castMap(value, path).entrySet()) {
                normalized.put(entry.getKey(), uniqueValue(
                        entry.getValue(), childPath(path, entry.getKey()), depth + 1, counter));
            }
            return normalized;
        }
        return value;
    }

    private void validateEnum(Map<String, Object> schema, Object value, String path) {
        if (!schema.containsKey(KEY_ENUM)) {
            return;
        }
        List<?> allowedValues = optionalList(schema.get(KEY_ENUM), path, KEY_ENUM);
        if (allowedValues.isEmpty() || allowedValues.stream().noneMatch(allowed -> valuesEqual(allowed, value))) {
            throw failure(Code.VALUE_INVALID, path, "value is not in enum");
        }
    }

    /** 数值上下界只允许出现在 number/integer Schema，边界本身必须有限且顺序有效。 */
    private void validateNumericBoundsSchema(Map<String, Object> schema,
            String expectedType, String path) {
        if (!schema.containsKey(KEY_MINIMUM) && !schema.containsKey(KEY_MAXIMUM)) {
            return;
        }
        if (!TYPE_NUMBER.equals(expectedType) && !TYPE_INTEGER.equals(expectedType)) {
            throw failure(Code.SCHEMA_INVALID, path,
                    "minimum and maximum require number or integer type");
        }
        BigDecimal minimum = optionalDecimal(schema, KEY_MINIMUM, path, Code.SCHEMA_INVALID);
        BigDecimal maximum = optionalDecimal(schema, KEY_MAXIMUM, path, Code.SCHEMA_INVALID);
        if (minimum != null && maximum != null && minimum.compareTo(maximum) > 0) {
            throw failure(Code.SCHEMA_INVALID, path, "minimum must not exceed maximum");
        }
    }

    /** 实例值按 JSON 数值语义比较，不依赖 Integer/Long/Double 的具体 Java 实现类型。 */
    private void validateNumericBounds(Map<String, Object> schema, Object value, String path) {
        if (!schema.containsKey(KEY_MINIMUM) && !schema.containsKey(KEY_MAXIMUM)) {
            return;
        }
        BigDecimal actual = decimal(value, path, "value", Code.VALUE_INVALID);
        BigDecimal minimum = optionalDecimal(schema, KEY_MINIMUM, path, Code.SCHEMA_INVALID);
        if (minimum != null && actual.compareTo(minimum) < 0) {
            throw failure(Code.VALUE_INVALID, path, "value is less than minimum");
        }
        BigDecimal maximum = optionalDecimal(schema, KEY_MAXIMUM, path, Code.SCHEMA_INVALID);
        if (maximum != null && actual.compareTo(maximum) > 0) {
            throw failure(Code.VALUE_INVALID, path, "value exceeds maximum");
        }
    }

    private BigDecimal optionalDecimal(Map<String, Object> schema,
            String keyword, String path, Code failureCode) {
        if (!schema.containsKey(keyword)) {
            return null;
        }
        return decimal(schema.get(keyword), path, keyword, failureCode);
    }

    private BigDecimal decimal(Object value, String path, String field, Code failureCode) {
        if (!(value instanceof Number)) {
            throw failure(failureCode, path, field + " must be a finite number");
        }
        try {
            return new BigDecimal(String.valueOf(value));
        } catch (NumberFormatException exception) {
            throw failure(failureCode, path, field + " must be a finite number");
        }
    }

    private boolean matchesType(String expectedType, Object value) {
        switch (expectedType) {
            case TYPE_OBJECT:
                return value instanceof Map;
            case TYPE_ARRAY:
                return value instanceof List;
            case TYPE_STRING:
                return value instanceof String;
            case TYPE_NUMBER:
                return value instanceof Number;
            case TYPE_INTEGER:
                return value instanceof Number && isInteger((Number) value);
            case TYPE_BOOLEAN:
                return value instanceof Boolean;
            case TYPE_NULL:
                return value == null;
            default:
                return false;
        }
    }

    private boolean isInteger(Number value) {
        try {
            return new BigDecimal(String.valueOf(value)).stripTrailingZeros().scale() <= 0;
        } catch (NumberFormatException exception) {
            return false;
        }
    }

    private boolean valuesEqual(Object left, Object right) {
        if (left instanceof Number && right instanceof Number) {
            try {
                return new BigDecimal(String.valueOf(left))
                        .compareTo(new BigDecimal(String.valueOf(right))) == 0;
            } catch (NumberFormatException exception) {
                return false;
            }
        }
        return Objects.equals(left, right);
    }

    private String requiredString(Object value, String path, String field) {
        if (!(value instanceof String) || ((String) value).isEmpty()) {
            throw failure(Code.SCHEMA_INVALID, path, field + " must be a non-empty string");
        }
        return (String) value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> requiredMap(Object value, String path, String field) {
        if (!(value instanceof Map)) {
            throw failure(Code.SCHEMA_INVALID, path, field + " must be an object schema");
        }
        return (Map<String, Object>) value;
    }

    private Map<String, Object> optionalMap(Object value, String path, String field) {
        return value == null ? Collections.emptyMap() : requiredMap(value, path, field);
    }

    private List<?> optionalList(Object value, String path, String field) {
        if (value == null) {
            return Collections.emptyList();
        }
        if (!(value instanceof List)) {
            throw failure(Code.SCHEMA_INVALID, path, field + " must be an array");
        }
        return (List<?>) value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> castMap(Object value, String path) {
        if (!(value instanceof Map)) {
            throw failure(Code.VALUE_INVALID, path, "value must be an object");
        }
        return (Map<String, Object>) value;
    }

    private String childPath(String path, String field) {
        return path + "." + field;
    }

    private ValidationException failure(Code code, String path, String reason) {
        return failure(code, path, reason, Reason.OTHER);
    }

    private ValidationException failure(Code code, String path,
            String reason, Reason failureReason) {
        return new ValidationException(code, path, reason, failureReason);
    }

    public enum Code {
        SCHEMA_INVALID,
        SCHEMA_UNSUPPORTED,
        VALUE_INVALID
    }

    public enum Reason {
        REQUIRED_PROPERTY_MISSING,
        OTHER
    }

    /** 校验失败只暴露稳定分类与值路径，不携带原始参数。 */
    public static class ValidationException extends IllegalArgumentException {
        private final Code code;
        private final String path;
        private final Reason reason;

        ValidationException(Code code, String path, String message, Reason reason) {
            super(message);
            this.code = code;
            this.path = path;
            this.reason = reason;
        }

        public Code getCode() {
            return code;
        }

        public String getPath() {
            return path;
        }

        public Reason getReason() {
            return reason;
        }
    }

    private static final class Counter {
        private int visitedValues;
    }
}
