package dev.a2flow.management.storage.db.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import dev.a2flow.management.storage.db.SkillFactoryStorageConstants;
import dev.a2flow.management.storage.db.entity.SkillFactoryAuthoringSessionDO;

/**
 * Authoring Chat 会话 Mapper。
 */
@Mapper
public interface SkillFactoryAuthoringSessionMapper extends BaseMapper<SkillFactoryAuthoringSessionDO> {
}
