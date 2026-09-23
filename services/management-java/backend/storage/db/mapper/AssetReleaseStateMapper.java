package dev.a2flow.management.storage.db.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import dev.a2flow.management.storage.db.entity.AssetReleaseStateDO;

/**
 * SkillFactory 共享发布聚合 Mapper。
 *
 * <p>该 Mapper 只负责 `skill_asset_release_state` 的 DB 读写，不参与发布状态迁移、门禁和领域调用。
 */
@Mapper
public interface AssetReleaseStateMapper extends BaseMapper<AssetReleaseStateDO> {
}
