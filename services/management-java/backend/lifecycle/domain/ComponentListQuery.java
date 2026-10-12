package dev.a2flow.management.lifecycle.domain;

import java.util.Map;
import java.util.Locale;

/** 管理列表分页；绑定候选和运行态查询不使用此请求。 */
public record ComponentListQuery(String keyword, String assetType, String dslType,
        boolean enabledOnly, int page, int pageSize) {
    public static ComponentListQuery from(Map<String, String> params, boolean enabledOnly) {
        return new ComponentListQuery(text(params, "keyword"), filter(params, "assetType"),
                filter(params, "dslType"), enabledOnly,
                positive(params, "page", 1, Integer.MAX_VALUE), positive(params, "pageSize", 20, 100));
    }

    public long offset() {
        return (long) (page - 1) * pageSize;
    }

    private static String filter(Map<String, String> params, String key) {
        String value = text(params, key).toUpperCase(Locale.ROOT);
        return value.equals("ALL") ? "" : value;
    }

    private static String text(Map<String, String> params, String key) {
        return params == null || params.get(key) == null ? "" : params.get(key).trim();
    }

    private static int positive(Map<String, String> params, String key, int defaultValue, int maximum) {
        String raw = text(params, key);
        if (raw.isEmpty()) {
            return defaultValue;
        }
        try {
            int value = Integer.parseInt(raw);
            if (value > 0 && value <= maximum) {
                return value;
            }
        } catch (NumberFormatException ignored) {
            // 非法分页明确拒绝，不静默截断。
        }
        throw new IllegalArgumentException("INVALID_" + key);
    }
}
