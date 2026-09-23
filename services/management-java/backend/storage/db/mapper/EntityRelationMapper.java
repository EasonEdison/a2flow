package dev.a2flow.management.storage.db.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import dev.a2flow.management.storage.db.entity.EntityRelationDO;

/**
 * SkillFactory 通用实体关系 Mapper。
 *
 * <p>该 Mapper 只负责 `entity_relation` 表的单行访问。完整集合覆盖、版本复制、Repository mock
 * 和业务快照解析均由 Repository 或上层 Service 完成，Mapper 不承载关系语义和生命周期流程。
 */
@Mapper
public interface EntityRelationMapper extends BaseMapper<EntityRelationDO> {

}
