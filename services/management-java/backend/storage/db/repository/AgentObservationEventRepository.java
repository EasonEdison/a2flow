package dev.a2flow.management.storage.db.repository;

import java.util.List;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.google.common.collect.Lists;
import dev.a2flow.management.agentcore.enums.DeletedEnum;
import dev.a2flow.management.storage.db.entity.AgentObservationEventDO;
import dev.a2flow.management.storage.db.mapper.AgentObservationEventMapper;

import lombok.extern.slf4j.Slf4j;

/**
 * Agent observation Repository。
 *
 * <p>该类只负责通过 Mapper 写入 observation event，并提供最近可见事件、幂等事件和指定类型
 * 最新事件查询。它不压缩 prompt、不执行工具，也不决定哪些业务事件需要写 observation。
 */
@Repository
@Slf4j
public class AgentObservationEventRepository {

    private static final int DEFAULT_LIMIT = 10;
    private static final int MAX_LIMIT = 50;
    private static final int VISIBLE_TO_MODEL = 1;

    @Resource
    private AgentObservationEventMapper observationEventMapper;

    /**
     * 新增 observation 事件。
     */
    public AgentObservationEventDO insert(AgentObservationEventDO eventDO) {
        normalizeJsonColumns(eventDO);
        return insertDb(eventDO);
    }

    /**
     * 查询最近对模型可见的 observation 摘要。
     */
    public List<AgentObservationEventDO> listRecentVisible(String bizKey, String threadId, int limit) {
        return listRecentVisibleDb(bizKey, threadId, limit);
    }

    /**
     * 根据业务线程、来源和 action 幂等键查询 observation。
     */
    public AgentObservationEventDO findByDedupeKey(String bizKey, String threadId, String source,
            String idempotencyKey) {
        return findByDedupeKeyDb(bizKey, threadId, source, idempotencyKey);
    }

    /**
     * 查询某类 observation 的最新一条记录。
     */
    public AgentObservationEventDO findLatestByType(String bizKey, String threadId, String workspaceId,
            String observationType, String source) {
        return findLatestByTypeDb(bizKey, threadId, workspaceId, observationType, source);
    }

    private AgentObservationEventDO insertDb(AgentObservationEventDO eventDO) {
        try {
            int rows = observationEventMapper.insert(eventDO);
            if (rows <= 0) {
                throw new IllegalStateException("insert observation event failed");
            }
        } catch (DuplicateKeyException exception) {
            if (StringUtils.isNotBlank(eventDO.getIdempotencyKey())) {
                AgentObservationEventDO existing = findByDedupeKeyDb(
                        eventDO.getBizKey(), eventDO.getThreadId(), eventDO.getSource(),
                        eventDO.getIdempotencyKey());
                if (existing != null) {
                    log.info("Agent observation并发写入命中幂等记录, observationId={}, bizKey={}, threadId={}, "
                                    + "source={}",
                            existing.getObservationId(), existing.getBizKey(), existing.getThreadId(),
                            existing.getSource());
                    return existing;
                }
            }
            throw exception;
        }
        log.info("Agent observation已写入DB, observationId={}, bizKey={}, threadId={}, type={}, source={}",
                eventDO.getObservationId(), eventDO.getBizKey(), eventDO.getThreadId(),
                eventDO.getObservationType(), eventDO.getSource());
        return eventDO;
    }

    private List<AgentObservationEventDO> listRecentVisibleDb(String bizKey, String threadId, int limit) {
        if (StringUtils.isAnyBlank(bizKey, threadId)) {
            return Lists.newArrayList();
        }
        int safeLimit = limit <= 0 ? DEFAULT_LIMIT : Math.min(limit, MAX_LIMIT);
        LambdaQueryWrapper<AgentObservationEventDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(AgentObservationEventDO::getBizKey, bizKey)
                .eq(AgentObservationEventDO::getThreadId, threadId)
                .eq(AgentObservationEventDO::getVisibleToModel, VISIBLE_TO_MODEL)
                .eq(AgentObservationEventDO::getDeleted, DeletedEnum.VALID.getCode())
                .orderByDesc(AgentObservationEventDO::getId)
                .last("LIMIT " + safeLimit);
        List<AgentObservationEventDO> result = observationEventMapper.selectList(wrapper);
        log.info("Agent observation查询DB完成, bizKey={}, threadId={}, limit={}, resultCount={}",
                bizKey, threadId, safeLimit, result.size());
        return result;
    }

    private AgentObservationEventDO findByDedupeKeyDb(String bizKey, String threadId, String source,
            String idempotencyKey) {
        if (StringUtils.isAnyBlank(bizKey, threadId, source, idempotencyKey)) {
            return null;
        }
        LambdaQueryWrapper<AgentObservationEventDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(AgentObservationEventDO::getBizKey, bizKey)
                .eq(AgentObservationEventDO::getThreadId, threadId)
                .eq(AgentObservationEventDO::getSource, source)
                .eq(AgentObservationEventDO::getIdempotencyKey, idempotencyKey)
                .eq(AgentObservationEventDO::getDeleted, DeletedEnum.VALID.getCode())
                .orderByDesc(AgentObservationEventDO::getId)
                .last("LIMIT 1");
        List<AgentObservationEventDO> events = observationEventMapper.selectList(wrapper);
        AgentObservationEventDO result = events.isEmpty() ? null : events.get(0);
        if (result != null) {
            log.info("Agent observation命中DB幂等记录, observationId={}, bizKey={}, threadId={}, source={}",
                    result.getObservationId(), bizKey, threadId, source);
        }
        return result;
    }

    private AgentObservationEventDO findLatestByTypeDb(String bizKey, String threadId, String workspaceId,
            String observationType, String source) {
        if (StringUtils.isAnyBlank(bizKey, threadId, observationType, source)) {
            return null;
        }
        LambdaQueryWrapper<AgentObservationEventDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(AgentObservationEventDO::getBizKey, bizKey)
                .eq(AgentObservationEventDO::getThreadId, threadId)
                .eq(AgentObservationEventDO::getObservationType, observationType)
                .eq(AgentObservationEventDO::getSource, source)
                .eq(AgentObservationEventDO::getDeleted, DeletedEnum.VALID.getCode());
        if (StringUtils.isNotBlank(workspaceId)) {
            wrapper.eq(AgentObservationEventDO::getWorkspaceId, workspaceId);
        }
        wrapper.orderByDesc(AgentObservationEventDO::getId).last("LIMIT 1");
        List<AgentObservationEventDO> events = observationEventMapper.selectList(wrapper);
        AgentObservationEventDO result = events.isEmpty() ? null : events.get(0);
        log.info("Agent observation查询最新类型DB完成, bizKey={}, threadId={}, workspaceId={}, type={}, "
                        + "source={}, found={}",
                bizKey, threadId, workspaceId, observationType, source, result != null);
        return result;
    }

    /** 入库前校验原生 JSON 列，扩展属性空值统一写 NULL。 */
    private void normalizeJsonColumns(AgentObservationEventDO eventDO) {
        if (eventDO == null) {
            return;
        }
        eventDO
                .setStateDeltaJson(SkillFactoryJsonColumnSupport.required(
                        eventDO.getStateDeltaJson(), "stateDeltaJson"))
                .setAttribute(SkillFactoryJsonColumnSupport.nullable(
                        eventDO.getAttribute(), "attribute"));
    }

}
