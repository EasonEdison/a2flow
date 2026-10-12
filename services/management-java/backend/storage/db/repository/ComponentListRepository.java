package dev.a2flow.management.storage.db.repository;

import java.util.List;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import dev.a2flow.management.lifecycle.ManagementListPage;
import dev.a2flow.management.lifecycle.domain.ComponentListItem;
import dev.a2flow.management.lifecycle.domain.ComponentListQuery;
import dev.a2flow.management.storage.db.mapper.ComponentListMapper;

@Repository
public class ComponentListRepository {
    @Resource
    private ComponentListMapper mapper;

    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public ManagementListPage<ComponentListItem> list(ComponentListQuery query) {
        long total = mapper.count(query);
        return new ManagementListPage<>(total == 0 ? List.of() : mapper.selectPage(query),
                total, query.page(), query.pageSize());
    }
}
