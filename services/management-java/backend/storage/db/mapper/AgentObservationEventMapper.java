package dev.a2flow.management.storage.db.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import dev.a2flow.management.storage.db.SkillFactoryStorageConstants;
import dev.a2flow.management.storage.db.entity.AgentObservationEventDO;

/**
 * Agent observation Mapper。
 *
 * <p>该 Mapper 只负责 `agent_observation_event` 的 DO 持久化。模型上下文压缩、脱敏和业务动作
 * 分发均不属于 Mapper 职责。
 */
@Mapper
public interface AgentObservationEventMapper extends BaseMapper<AgentObservationEventDO> {
}
