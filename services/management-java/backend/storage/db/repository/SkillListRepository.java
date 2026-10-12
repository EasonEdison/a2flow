package dev.a2flow.management.storage.db.repository;

import java.util.List;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import dev.a2flow.management.lifecycle.SkillListPage;
import dev.a2flow.management.lifecycle.domain.SkillListQuery;
import dev.a2flow.management.storage.db.mapper.SkillListMapper;

/** 同一只读快照返回分页和计数，不加载工作区或发布历史。 */
@Repository
public class SkillListRepository {
    @Resource
    private SkillListMapper mapper;

    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public SkillListPage list(SkillListQuery query) {
        SkillListMapper.Counts counts = mapper.count(query);
        if (counts.getInvalidStateCount() > 0) {
            throw new IllegalStateException("Invalid or missing persisted workspace release state");
        }
        return new SkillListPage(counts.getTotal() == 0 ? List.of() : mapper.selectPage(query),
                counts.getTotal(), query.page(), query.pageSize(), counts.getEditingCount(), counts.getOnlineCount());
    }
}
