package dev.a2flow.management.storage.db.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import dev.a2flow.management.storage.db.entity.CapabilityActionDraftDO;

/**
 * 能力中心草稿 Mapper。
 *
 * <p>该 Mapper 只承接草稿表的 DB 读写。草稿校验、发布门禁、AI 增量合并和外部接口执行均由
 * 上层 Repository/Service 完成，避免 Mapper 承担业务流程。
 */
@Mapper
public interface CapabilityActionDraftMapper extends BaseMapper<CapabilityActionDraftDO> {

}
