package dev.a2flow.management.model;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 按JSON Schema整数语义检查并无损规范请求值，不截断小数，不改写number字段。 */
public final class CapabilityIntegerSupport {
    private CapabilityIntegerSupport() {
    }

    /** 只接受有限且数学上没有小数部分的JSON数字。 */
    public static boolean isInteger(Object value) {
        if (!(value instanceof Number)) {
            return false;
        }
        try {
            new BigDecimal(value.toString()).toBigIntegerExact();
            return true;
        } catch (NumberFormatException | ArithmeticException exception) {
            return false;
        }
    }

    /** 递归生成新值，避免修改冻结计划中的常量或原始参数。 */
    public static Object normalize(Object value, Map<String, Object> schema) {
        if (value == null) {
            return null;
        }
        String type = String.valueOf(schema.get("type"));
        if ("integer".equals(type)) {
            if (!isInteger(value)) {
                throw new IllegalArgumentException("整数参数必须是无小数部分的数字");
            }
            return new BigDecimal(value.toString()).toBigIntegerExact();
        }
        if ("array".equals(type) && value instanceof List) {
            List<Object> result = new ArrayList<>();
            for (Object item : (List<?>) value) {
                result.add(normalize(item, schemaMap(schema.get("items"))));
            }
            return result;
        }
        if ("object".equals(type) && value instanceof Map) {
            Map<String, Object> properties = schemaMap(schema.get("properties"));
            Map<String, Object> result = new LinkedHashMap<>();
            schemaMap(value).forEach((key, item) ->
                    result.put(key, normalize(item, schemaMap(properties.get(key)))));
            return result;
        }
        return value;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> schemaMap(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Map.of();
    }
}
