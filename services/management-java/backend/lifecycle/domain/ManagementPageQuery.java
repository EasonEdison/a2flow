package dev.a2flow.management.lifecycle.domain;

import java.util.Map;

/** 管理列表统一页码边界，不影响绑定候选和发布列表。 */
public record ManagementPageQuery(int page, int pageSize) {
    public static ManagementPageQuery from(Map<String, String> params) {
        return new ManagementPageQuery(positive(params, "page", 1, Integer.MAX_VALUE),
                positive(params, "pageSize", 20, 100));
    }

    public long offset() {
        return (long) (page - 1) * pageSize;
    }

    private static int positive(Map<String, String> params, String key, int fallback, int maximum) {
        String raw = params == null ? null : params.get(key);
        if (raw == null || raw.isBlank()) return fallback;
        try {
            int value = Integer.parseInt(raw.trim());
            if (value > 0 && value <= maximum) return value;
        } catch (NumberFormatException ignored) {
            // Reject malformed paging rather than changing the requested result set.
        }
        throw new IllegalArgumentException("INVALID_" + key);
    }
}
