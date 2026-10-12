package dev.a2flow.management.storage.db.mapper;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import dev.a2flow.management.lifecycle.domain.ComponentListItem;
import dev.a2flow.management.lifecycle.domain.ComponentListQuery;

@Mapper
public interface ComponentListMapper {
    List<ComponentListItem> selectPage(@Param("query") ComponentListQuery query);
    long count(@Param("query") ComponentListQuery query);
}
