package dev.a2flow.management.a2ui.application;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.release.ReleaseDigestUtils;

/**
 * A2UI Application 编译期 JSON 规范化与深冻结工具。
 *
 * <p>只处理内存快照，不读取文件、数据库或网络；compiler 用它生成确定性 digest 并切断 Build 与
 * mutable draft 的引用。本工具不解析协议语义，也不通过丢字段实现兼容或降级。
 */
public final class A2uiImmutableJsonSupport {

    private static final String DIGEST_PREFIX = "sha256:";

    private A2uiImmutableJsonSupport() {
    }

    public static String digest(Object value) {
        return DIGEST_PREFIX + ReleaseDigestUtils.sha256(JsonSupport.toJSON(canonicalize(value)));
    }

    public static Object canonicalize(Object value) {
        if (value instanceof Map) {
            Map<String, Object> canonical = new TreeMap<>();
            ((Map<?, ?>) value).forEach((key, child) ->
                    canonical.put(String.valueOf(key), canonicalize(child)));
            return canonical;
        }
        if (value instanceof List) {
            List<Object> canonical = new ArrayList<>();
            for (Object child : (List<?>) value) {
                canonical.add(canonicalize(child));
            }
            return canonical;
        }
        if (value == null || value instanceof String || value instanceof Number || value instanceof Boolean) {
            return value;
        }
        Object objectMap = JsonSupport.fromJSON(JsonSupport.toJSON(value), Map.class);
        return canonicalize(objectMap);
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> immutableMap(Map<String, ?> source) {
        if (source == null) {
            return null;
        }
        return (Map<String, Object>) immutableValue(source);
    }

    static Map<String, String> immutableStringMap(Map<String, String> source) {
        return Collections.unmodifiableMap(new TreeMap<>(source));
    }

    static List<String> immutableStringList(List<String> source) {
        return Collections.unmodifiableList(new ArrayList<>(source));
    }

    @SuppressWarnings("unchecked")
    static List<Map<String, Object>> immutableMessageList(List<Map<String, Object>> source) {
        return (List<Map<String, Object>>) (List<?>) immutableValue(source);
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
