package dev.a2flow.management.storage.db.repository;

import java.util.List;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import dev.a2flow.management.authoring.session.domain.AuthoringStreamEvent;
import dev.a2flow.management.authoring.session.domain.AuthoringStreamEventRepository;
import dev.a2flow.management.storage.db.entity.SkillFactoryAuthoringEventDO;
import dev.a2flow.management.storage.db.mapper.SkillFactoryAuthoringEventMapper;
import dev.a2flow.management.storage.db.mapper.SkillFactoryMapperConstants;

import lombok.extern.slf4j.Slf4j;

/**
 * Authoring Chat 结构化流式事件仓储的 MySQL 实现。
 *
 * <p>该类按结构化协议字段保存事件，不把整条事件压进 content，也不负责 session 摘要和前端渲染。
 */
@Repository
@Slf4j
public class SkillFactoryAuthoringStreamEventDbRepository implements AuthoringStreamEventRepository {

    private static final int NOT_DELETED = 0;
    private static final int TRUE_VALUE = 1;
    private static final int FALSE_VALUE = 0;
    private static final String INSERT_FAILED_MESSAGE = "insert authoring event failed";

    @Resource
    private SkillFactoryAuthoringEventMapper eventMapper;

    /**
     * 幂等写入一条结构化流式事件。
     */
    @Override
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public boolean append(AuthoringStreamEvent event) {
        if (event == null || StringUtils.isAnyBlank(event.getRecordId(), event.getSessionId())) {
            return false;
        }
        if (exists(event.getRecordId())) {
            log.info("SkillFactory Authoring Chat跳过重复事件, sessionId={}, recordId={}",
                    event.getSessionId(), event.getRecordId());
            return false;
        }
        long timestamp = event.getTimestamp() > 0 ? event.getTimestamp() : System.currentTimeMillis();
        try {
            if (eventMapper.insert(toDO(event, timestamp)) <= 0) {
                throw new IllegalStateException(INSERT_FAILED_MESSAGE);
            }
        } catch (DuplicateKeyException exception) {
            log.info("SkillFactory Authoring Chat并发写入重复事件，按幂等成功处理, sessionId={}, recordId={}",
                    event.getSessionId(), event.getRecordId());
            return false;
        }
        log.info("SkillFactory Authoring Chat事件已写入DB, sessionId={}, recordId={}, "
                        + "eventType={}, payloadType={}",
                event.getSessionId(), event.getRecordId(), event.getEventType(), event.getPayloadType());
        return true;
    }

    /**
     * 按时间正序查询会话流式事件。
     */
    @Override
    public List<AuthoringStreamEvent> listBySessionId(String sessionId) {
        LambdaQueryWrapper<SkillFactoryAuthoringEventDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryAuthoringEventDO::getSessionId, sessionId)
                .eq(SkillFactoryAuthoringEventDO::getDeleted, NOT_DELETED)
                .orderByAsc(SkillFactoryAuthoringEventDO::getTimestamp)
                .orderByAsc(SkillFactoryAuthoringEventDO::getId);
        return eventMapper.selectList(wrapper).stream().map(this::toDomain).collect(Collectors.toList());
    }

    /**
     * 查询指定 invoke 的公开事件日志，运行控制服务据此推导持久化开始/终态。
     */
    @Override
    public List<AuthoringStreamEvent> listByRun(String sessionId, String invokeId) {
        LambdaQueryWrapper<SkillFactoryAuthoringEventDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryAuthoringEventDO::getSessionId, sessionId)
                .eq(SkillFactoryAuthoringEventDO::getInvokeId, invokeId)
                .eq(SkillFactoryAuthoringEventDO::getDeleted, NOT_DELETED)
                .orderByAsc(SkillFactoryAuthoringEventDO::getTimestamp)
                .orderByAsc(SkillFactoryAuthoringEventDO::getId);
        return eventMapper.selectList(wrapper).stream().map(this::toDomain).collect(Collectors.toList());
    }

    private boolean exists(String recordId) {
        LambdaQueryWrapper<SkillFactoryAuthoringEventDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryAuthoringEventDO::getRecordId, recordId)
                .eq(SkillFactoryAuthoringEventDO::getDeleted, NOT_DELETED);
        return eventMapper.selectCount(wrapper) > 0;
    }

    private AuthoringStreamEvent toDomain(SkillFactoryAuthoringEventDO eventDO) {
        return new AuthoringStreamEvent()
                .setRecordId(eventDO.getRecordId())
                .setSessionId(eventDO.getSessionId())
                .setSchemaVersion(eventDO.getSchemaVersion())
                .setEventType(eventDO.getEventType())
                .setEventId(eventDO.getEventId())
                .setBlockId(eventDO.getBlockId())
                .setSource(eventDO.getSource())
                .setWorkspaceId(eventDO.getWorkspaceId())
                .setInvokeId(eventDO.getInvokeId())
                .setMessageId(eventDO.getMessageId())
                .setRunId(eventDO.getRunId())
                .setConversationId(eventDO.getConversationId())
                .setThreadId(eventDO.getThreadId())
                .setTraceId(eventDO.getTraceId())
                .setModelContentBlockJson(eventDO.getModelContentBlockJson())
                .setPayloadType(eventDO.getPayloadType())
                .setPayloadJson(eventDO.getPayloadJson())
                .setContent(eventDO.getContent())
                .setToolCallId(eventDO.getToolCallId())
                .setToolName(eventDO.getToolName())
                .setToolArgs(eventDO.getToolArgs())
                .setToolSuccess(Integer.valueOf(TRUE_VALUE).equals(eventDO.getToolSuccess()))
                .setTokenCount(defaultLong(eventDO.getTokenCount()))
                .setEnterTokenCount(defaultLong(eventDO.getEnterTokenCount()))
                .setOutputTokenCount(defaultLong(eventDO.getOutputTokenCount()))
                .setHasKnowledge(Integer.valueOf(TRUE_VALUE).equals(eventDO.getHasKnowledge()))
                .setTimestamp(defaultLong(eventDO.getTimestamp()))
                .setAnswerAgentId(defaultLong(eventDO.getAnswerAgentId()));
    }

    private SkillFactoryAuthoringEventDO toDO(AuthoringStreamEvent event, long timestamp) {
        return new SkillFactoryAuthoringEventDO()
                .setRecordId(event.getRecordId())
                .setSessionId(event.getSessionId())
                .setSchemaVersion(event.getSchemaVersion())
                .setEventType(event.getEventType())
                .setEventId(event.getEventId())
                .setBlockId(event.getBlockId())
                .setSource(event.getSource())
                .setWorkspaceId(event.getWorkspaceId())
                .setInvokeId(event.getInvokeId())
                .setMessageId(event.getMessageId())
                .setRunId(event.getRunId())
                .setConversationId(event.getConversationId())
                .setThreadId(event.getThreadId())
                .setTraceId(event.getTraceId())
                .setModelContentBlockJson(SkillFactoryJsonColumnSupport.nullable(
                        event.getModelContentBlockJson(), "modelContentBlockJson"))
                .setPayloadType(event.getPayloadType())
                .setPayloadJson(SkillFactoryJsonColumnSupport.nullable(
                        event.getPayloadJson(), "payloadJson"))
                .setContent(event.getContent())
                .setToolCallId(event.getToolCallId())
                .setToolName(event.getToolName())
                .setToolArgs(SkillFactoryJsonColumnSupport.nullable(event.getToolArgs(), "toolArgs"))
                .setToolSuccess(event.isToolSuccess() ? TRUE_VALUE : FALSE_VALUE)
                .setTokenCount(event.getTokenCount())
                .setEnterTokenCount(event.getEnterTokenCount())
                .setOutputTokenCount(event.getOutputTokenCount())
                .setHasKnowledge(event.isHasKnowledge() ? TRUE_VALUE : FALSE_VALUE)
                .setTimestamp(timestamp)
                .setAnswerAgentId(event.getAnswerAgentId())
                .setDeleted(NOT_DELETED)
                .setCreateTime(timestamp)
                .setUpdateTime(timestamp);
    }

    private long defaultLong(Long value) {
        return value == null ? 0L : value;
    }
}
