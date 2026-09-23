package dev.a2flow.management.storage.db.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import dev.a2flow.management.storage.db.entity.SkillAssetPrincipalDO;

/**
 * SkillFactory 通用资产成员 Mapper。
 *
 * <p>该 Mapper 只负责 {@code skill_asset_principal} 单表读写；负责人集合替换、状态迁移和授权策略
 * 由 Repository 与权限 Service 负责。
 */
@Mapper
public interface SkillAssetPrincipalMapper extends BaseMapper<SkillAssetPrincipalDO> {
}
