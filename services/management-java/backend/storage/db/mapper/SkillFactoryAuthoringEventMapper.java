package dev.a2flow.management.storage.db.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import dev.a2flow.management.storage.db.SkillFactoryStorageConstants;
import dev.a2flow.management.storage.db.entity.SkillFactoryAuthoringEventDO;

/**
 * Authoring Chat 结构化流式事件 Mapper。
 */
@Mapper
public interface SkillFactoryAuthoringEventMapper extends BaseMapper<SkillFactoryAuthoringEventDO> {
}
