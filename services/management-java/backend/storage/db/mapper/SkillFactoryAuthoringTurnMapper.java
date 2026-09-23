package dev.a2flow.management.storage.db.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import dev.a2flow.management.storage.db.SkillFactoryStorageConstants;
import dev.a2flow.management.storage.db.entity.SkillFactoryAuthoringTurnDO;

/**
 * Authoring Chat 对话 turn Mapper。
 */
@Mapper
public interface SkillFactoryAuthoringTurnMapper extends BaseMapper<SkillFactoryAuthoringTurnDO> {
}
