package dev.a2flow.management.lifecycle.domain;

import java.util.Map;

/** 列表入参只在 HTTP 边界解析一次，分页范围由服务端限制。 */
public record SkillListQuery(String keyword, String businessDomain, String capabilityDomain,
        String specialistId, String status, int page, int pageSize) {
    public static SkillListQuery from(Map<String, String> params) {
        String status = text(params, "status");
        if (!status.isEmpty() && !status.equals("EDITING") && !status.equals("ONLINE")) {
            throw new IllegalArgumentException("INVALID_SKILL_STATUS_FILTER");
        }
        return new SkillListQuery(text(params, "keyword"), text(params, "businessDomain"),
                text(params, "capabilityDomain"), text(params, "specialistId"), status,
                positive(params, "page", 1, Integer.MAX_VALUE), positive(params, "pageSize", 20, 100));
    }

    public long offset() {
        return (long) (page - 1) * pageSize;
    }

    private static String text(Map<String, String> params, String key) {
        return params == null || params.get(key) == null ? "" : params.get(key).trim();
    }

    private static int positive(Map<String, String> params, String key, int fallback, int maximum) {
        String raw = text(params, key);
        if (raw.isEmpty()) {
            return fallback;
        }
        try {
            int value = Integer.parseInt(raw);
            if (value > 0 && value <= maximum) {
                return value;
            }
        } catch (NumberFormatException ignored) {
            // 无效入参明确报错，不静默更改页码。
        }
        throw new IllegalArgumentException("INVALID_" + key);
    }
}
