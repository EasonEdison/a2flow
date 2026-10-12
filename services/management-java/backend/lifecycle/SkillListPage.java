package dev.a2flow.management.lifecycle;

import java.util.List;
import dev.a2flow.management.lifecycle.domain.SkillListItem;

/** Skill 列表的分页响应；空库也返回完整结构，不返回裸数组。 */
public record SkillListPage(List<SkillListItem> list, long total, int page,
        int pageSize, long editingCount, long onlineCount) { }
