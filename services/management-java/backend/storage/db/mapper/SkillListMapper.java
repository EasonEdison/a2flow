package dev.a2flow.management.storage.db.mapper;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import dev.a2flow.management.lifecycle.domain.SkillListItem;
import dev.a2flow.management.lifecycle.domain.SkillListQuery;
import lombok.Data;

@Mapper
public interface SkillListMapper {
    List<SkillListItem> selectPage(@Param("query") SkillListQuery query);
    Counts count(@Param("query") SkillListQuery query);

    @Data
    class Counts {
        private long total;
        private long editingCount;
        private long onlineCount;
        private long invalidStateCount;
    }
}
