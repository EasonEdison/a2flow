package dev.a2flow.management.a2ui.gateway;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import dev.a2flow.management.support.JsonSupport;

/**
 * Action Gateway 的结构化 JSON 复制工具。
 *
 * <p>上游 resolver/mapper 用它切断客户端或调用方可变 Map 引用，下游只接收深冻结 JSON-like 值。
 * 本类不做 schema/业务语义判断，不读取字符串 marker，也不通过丢字段实现兼容。
 */
final class A2uiGatewayJsonSupport {

    private A2uiGatewayJsonSupport() {
    }

    static JsonNode toNode(Object value) {
        return JsonSupport.mapper().valueToTree(value);
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> immutableMap(Map<String, ?> source) {
        return (Map<String, Object>) immutableValue(source);
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> immutableMap(JsonNode source) {
        Map<String, Object> value = JsonSupport.mapper().convertValue(source, Map.class);
        return (Map<String, Object>) immutableValue(value);
    }

    static Object immutableValue(Object value) {
        if (value instanceof Map) {
            Map<String, Object> copy = new LinkedHashMap<>();
            ((Map<?, ?>) value).forEach((key, child) ->
                    copy.put(String.valueOf(key), immutableValue(child)));
            return Collections.unmodifiableMap(copy);
        }
        if (value instanceof List) {
            List<Object> copy = new ArrayList<>();
            for (Object child : (List<?>) value) {
                copy.add(immutableValue(child));
            }
            return Collections.unmodifiableList(copy);
        }
        return value;
    }
}
