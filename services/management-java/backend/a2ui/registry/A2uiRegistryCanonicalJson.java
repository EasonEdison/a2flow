package dev.a2flow.management.a2ui.registry;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.release.ReleaseDigestUtils;

/**
 * A2UI Registry canonical JSON 工具。
 *
 * <p>Map 按 key 排序、List 保留作者顺序，再以 UTF-8 JSON 计算 digest。该工具不删除未知字段，
 * 不从旧 CARD_CONTAINER / BUSINESS_DSL 资产推导 A2UI contract。
 */
final class A2uiRegistryCanonicalJson {

    private static final String DIGEST_PREFIX = "sha256:";

    private A2uiRegistryCanonicalJson() {
    }

    static Object canonicalize(Object value) {
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
        if (value == null || value instanceof String || value instanceof Number
                || value instanceof Boolean) {
            return value;
        }
        return canonicalize(JsonSupport.fromJSON(JsonSupport.toJSON(value), Map.class));
    }

    static String json(Object value) {
        return JsonSupport.toJSON(canonicalize(value));
    }

    static String digest(Object value) {
        return DIGEST_PREFIX + ReleaseDigestUtils.sha256(json(value));
    }
}
