package dev.a2flow.management.lifecycle;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

/** Skill 列表的分页响应；空库也返回完整结构，不返回裸数组。 */
public record SkillListPage(List<Map<String, Object>> list, long total, int page,
        int pageSize, long editingCount, long onlineCount) {
    public static SkillListPage from(List<Map<String, Object>> rows, Map<String, String> params) {
        int page = positive(params, "page", 1, Integer.MAX_VALUE);
        int size = positive(params, "pageSize", 20, 100);
        String specialist = params.getOrDefault("specialistId", "").trim();
        String status = params.getOrDefault("status", "").trim();
        if (!status.isEmpty() && !status.equals("EDITING") && !status.equals("ONLINE")) {
            throw new IllegalArgumentException("INVALID_SKILL_STATUS_FILTER");
        }
        List<Map<String, Object>> scoped = rows.stream().filter(row -> specialist.isEmpty()
                || Arrays.stream(text(row, "specialistId").split(","))
                    .map(String::trim).anyMatch(specialist::equals)).toList();
        long editing = scoped.stream().filter(SkillListPage::editing).count();
        long online = scoped.stream().filter(SkillListPage::online).count();
        List<Map<String, Object>> filtered = scoped.stream().filter(row -> status.isEmpty()
                || (status.equals("EDITING") ? editing(row) : online(row))).toList();
        long offset = (long) (page - 1) * size;
        return new SkillListPage(filtered.stream().skip(offset).limit(size).toList(),
                filtered.size(), page, size, editing, online);
    }

    private static boolean editing(Map<String, Object> row) {
        return "EDITING".equals(text(row, "draftStatus"));
    }

    private static boolean online(Map<String, Object> row) {
        return !text(row, "onlineVersionId").isBlank();
    }

    private static String text(Map<String, Object> row, String key) {
        Object value = row.get(key);
        return value == null ? "" : value.toString();
    }

    private static int positive(Map<String, String> params, String key, int fallback, int maximum) {
        String raw = params.get(key);
        if (raw == null || raw.isBlank()) return fallback;
        try {
            int value = Integer.parseInt(raw);
            if (value > 0 && value <= maximum) return value;
        } catch (NumberFormatException ignored) {
            // Report a contract error rather than silently changing the requested page.
        }
        throw new IllegalArgumentException("INVALID_" + key);
    }
}
