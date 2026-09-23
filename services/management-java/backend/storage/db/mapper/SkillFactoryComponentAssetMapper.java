package dev.a2flow.management.storage.db.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import dev.a2flow.management.storage.db.entity.SkillFactoryComponentAssetDO;

/**
 * SkillFactory 组件资产 Mapper。
 *
 * <p>该 Mapper 只负责 `skill_component_registry` 表的数据访问。组件协议校验、官方 demo 预览
 * 和领域转换不放在 Mapper 中；组件中心不提供种子数据或 DB 失败兜底。
 */
@Mapper
public interface SkillFactoryComponentAssetMapper extends BaseMapper<SkillFactoryComponentAssetDO> {

}
