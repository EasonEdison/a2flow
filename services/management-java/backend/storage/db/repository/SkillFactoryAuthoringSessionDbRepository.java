package dev.a2flow.management.storage.db.repository;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import dev.a2flow.management.authoring.session.domain.AuthoringSession;
import dev.a2flow.management.authoring.session.domain.AuthoringSessionRepository;
import dev.a2flow.management.authoring.session.domain.AuthoringSessionScope;
import dev.a2flow.management.storage.db.entity.SkillFactoryAuthoringSessionDO;
import dev.a2flow.management.storage.db.mapper.SkillFactoryAuthoringSessionMapper;
import dev.a2flow.management.storage.db.mapper.SkillFactoryMapperConstants;

import lombok.extern.slf4j.Slf4j;

/**
 * Authoring Chat 会话领域仓储的 MySQL 实现。
 *
 * <p>该实现只通过会话 Mapper 访问会话 DO，并在存储对象与领域对象之间转换。turn/event 明细由各自
 * 仓储负责；该实现只管理会话激活、标题、消息数和最近沟通时间。
 */
@Repository
@Slf4j
@SuppressWarnings("checkstyle:MagicNumber")
public class SkillFactoryAuthoringSessionDbRepository implements AuthoringSessionRepository {

    private static final DateTimeFormatter SESSION_TIME_FORMATTER =
            DateTimeFormatter.ofPattern("yyyyMMddHHmmss");
    private static final int TITLE_MAX_LENGTH = 40;
    private static final int NOT_DELETED = 0;
    private static final int ACTIVE = 1;
    private static final int INACTIVE = 0;
    private static final String SESSION_ID_PREFIX = "sf_chat_";
    private static final String UNKNOWN_SCOPE_VALUE = "unknown";
    private static final String INSERT_FAILED_MESSAGE = "insert authoring session failed";
    private static final String SESSION_NOT_FOUND_MESSAGE = "authoring session not found";

    @Resource
    private SkillFactoryAuthoringSessionMapper sessionMapper;

    /**
     * 确保请求会话属于当前 scope，并将它设置为活跃会话。
     */
    @Override
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public AuthoringSession ensureSession(AuthoringSessionScope scope, String sessionId) {
        SkillFactoryAuthoringSessionDO target;
        if (StringUtils.isBlank(sessionId)) {
            target = resolveCurrentSession(scope);
        } else {
            target = findSessionDO(scope, sessionId);
            if (target == null) {
                target = resolveCurrentSession(scope);
                log.info("SkillFactory Authoring Chat忽略未知客户端sessionId并使用后端会话, "
                                + "scopeKey={}, requestedSessionId={}, resolvedSessionId={}",
                        scope.scopeKey(), sessionId, target.getSessionId());
            }
        }
        activateSession(scope, target.getSessionId());
        target.setActive(ACTIVE).setUpdateTime(System.currentTimeMillis());
        return toDomain(target);
    }

    /**
     * 创建并激活新会话，旧会话保留为历史。
     */
    @Override
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public AuthoringSession createNewSession(AuthoringSessionScope scope) {
        SkillFactoryAuthoringSessionDO created = insertSession(scope, newSessionId(scope));
        activateSession(scope, created.getSessionId());
        log.info("SkillFactory Authoring Chat已创建DB session, scopeKey={}, sessionId={}",
                scope.scopeKey(), created.getSessionId());
        return toDomain(created);
    }

    /**
     * 查询 scope 下的全部会话。
     */
    @Override
    public List<AuthoringSession> listSessions(AuthoringSessionScope scope) {
        return listSessionDOs(scope).stream().map(this::toDomain).collect(Collectors.toList());
    }

    /**
     * 查询 scope 下的指定会话。
     */
    @Override
    public AuthoringSession findSession(AuthoringSessionScope scope, String sessionId) {
        SkillFactoryAuthoringSessionDO sessionDO = findSessionDO(scope, sessionId);
        return sessionDO == null ? null : toDomain(sessionDO);
    }

    /**
     * turn 写入成功后维护会话摘要。
     */
    @Override
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public void recordTurn(AuthoringSessionScope scope, String sessionId, long timestamp,
            String titleCandidate) {
        touchSession(scope, sessionId, timestamp, titleCandidate, true);
    }

    /**
     * 完整 Assistant turn 写入成功后维护最近沟通时间，不重复增加用户消息数。
     */
    @Override
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public void recordAssistantTurn(AuthoringSessionScope scope, String sessionId, long timestamp) {
        touchSession(scope, sessionId, timestamp, null, false);
    }

    /**
     * 终态 event 写入成功后兜底维护最近活动时间。
     */
    @Override
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public void recordEvent(AuthoringSessionScope scope, String sessionId, long timestamp) {
        touchSession(scope, sessionId, timestamp, null, false);
    }

    private SkillFactoryAuthoringSessionDO insertSession(AuthoringSessionScope scope, String sessionId) {
        long now = System.currentTimeMillis();
        SkillFactoryAuthoringSessionDO sessionDO = new SkillFactoryAuthoringSessionDO()
                .setSessionId(sessionId)
                .setBizKey(scope.getBizKey())
                .setScopeType(scope.getScopeType())
                .setScopeId(scope.getScopeId())
                .setWorkspaceId(scope.getWorkspaceId())
                .setTitle(StringUtils.EMPTY)
                .setCreator(StringUtils.defaultString(scope.getOperator()))
                .setLastOperator(StringUtils.defaultString(scope.getOperator()))
                .setActive(ACTIVE)
                .setMessageCount(0L)
                .setLastMessageTime(now)
                .setDeleted(NOT_DELETED)
                .setCreateTime(now)
                .setUpdateTime(now);
        int rows = sessionMapper.insert(sessionDO);
        if (rows <= 0) {
            throw new IllegalStateException(INSERT_FAILED_MESSAGE);
        }
        return sessionDO;
    }

    private SkillFactoryAuthoringSessionDO resolveCurrentSession(AuthoringSessionScope scope) {
        SkillFactoryAuthoringSessionDO activeSession = findActiveSession(scope);
        if (activeSession != null) {
            return activeSession;
        }
        List<SkillFactoryAuthoringSessionDO> sessions = listSessionDOs(scope);
        return sessions.isEmpty() ? insertSession(scope, newSessionId(scope)) : sessions.get(0);
    }

    private SkillFactoryAuthoringSessionDO findActiveSession(AuthoringSessionScope scope) {
        LambdaQueryWrapper<SkillFactoryAuthoringSessionDO> wrapper = scopeQuery(scope)
                .eq(SkillFactoryAuthoringSessionDO::getActive, ACTIVE)
                .orderByDesc(SkillFactoryAuthoringSessionDO::getLastMessageTime)
                .orderByDesc(SkillFactoryAuthoringSessionDO::getId)
                .last("LIMIT 1");
        List<SkillFactoryAuthoringSessionDO> sessions = sessionMapper.selectList(wrapper);
        return sessions.isEmpty() ? null : sessions.get(0);
    }

    private SkillFactoryAuthoringSessionDO findSessionDO(AuthoringSessionScope scope, String sessionId) {
        if (StringUtils.isBlank(sessionId)) {
            return null;
        }
        LambdaQueryWrapper<SkillFactoryAuthoringSessionDO> wrapper = scopeQuery(scope)
                .eq(SkillFactoryAuthoringSessionDO::getSessionId, sessionId)
                .last("LIMIT 1");
        List<SkillFactoryAuthoringSessionDO> sessions = sessionMapper.selectList(wrapper);
        return sessions.isEmpty() ? null : sessions.get(0);
    }

    private List<SkillFactoryAuthoringSessionDO> listSessionDOs(AuthoringSessionScope scope) {
        return sessionMapper.selectList(scopeQuery(scope)
                .orderByDesc(SkillFactoryAuthoringSessionDO::getLastMessageTime)
                .orderByDesc(SkillFactoryAuthoringSessionDO::getId));
    }

    private LambdaQueryWrapper<SkillFactoryAuthoringSessionDO> scopeQuery(AuthoringSessionScope scope) {
        return new LambdaQueryWrapper<SkillFactoryAuthoringSessionDO>()
                .eq(SkillFactoryAuthoringSessionDO::getBizKey, scope.getBizKey())
                .eq(SkillFactoryAuthoringSessionDO::getScopeType, scope.getScopeType())
                .eq(SkillFactoryAuthoringSessionDO::getScopeId, scope.getScopeId())
                .eq(SkillFactoryAuthoringSessionDO::getDeleted, NOT_DELETED);
    }

    private void activateSession(AuthoringSessionScope scope, String sessionId) {
        long now = System.currentTimeMillis();
        LambdaUpdateWrapper<SkillFactoryAuthoringSessionDO> deactivate = new LambdaUpdateWrapper<>();
        deactivate.eq(SkillFactoryAuthoringSessionDO::getBizKey, scope.getBizKey())
                .eq(SkillFactoryAuthoringSessionDO::getScopeType, scope.getScopeType())
                .eq(SkillFactoryAuthoringSessionDO::getScopeId, scope.getScopeId())
                .eq(SkillFactoryAuthoringSessionDO::getDeleted, NOT_DELETED)
                .set(SkillFactoryAuthoringSessionDO::getActive, INACTIVE)
                .set(SkillFactoryAuthoringSessionDO::getLastOperator,
                        StringUtils.defaultString(scope.getOperator()))
                .set(SkillFactoryAuthoringSessionDO::getUpdateTime, now);
        sessionMapper.update(null, deactivate);

        LambdaUpdateWrapper<SkillFactoryAuthoringSessionDO> activate = new LambdaUpdateWrapper<>();
        activate.eq(SkillFactoryAuthoringSessionDO::getSessionId, sessionId)
                .eq(SkillFactoryAuthoringSessionDO::getDeleted, NOT_DELETED)
                .set(SkillFactoryAuthoringSessionDO::getActive, ACTIVE)
                .set(SkillFactoryAuthoringSessionDO::getLastOperator,
                        StringUtils.defaultString(scope.getOperator()))
                .set(SkillFactoryAuthoringSessionDO::getUpdateTime, now);
        sessionMapper.update(null, activate);
    }

    private void touchSession(AuthoringSessionScope scope, String sessionId, long timestamp,
            String titleCandidate, boolean incrementMessageCount) {
        SkillFactoryAuthoringSessionDO current = findSessionDO(scope, sessionId);
        if (current == null) {
            throw new IllegalStateException(SESSION_NOT_FOUND_MESSAGE);
        }
        LambdaUpdateWrapper<SkillFactoryAuthoringSessionDO> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(SkillFactoryAuthoringSessionDO::getSessionId, sessionId)
                .eq(SkillFactoryAuthoringSessionDO::getDeleted, NOT_DELETED)
                .set(SkillFactoryAuthoringSessionDO::getLastMessageTime, timestamp)
                .set(SkillFactoryAuthoringSessionDO::getLastOperator,
                        StringUtils.defaultString(scope.getOperator()))
                .set(SkillFactoryAuthoringSessionDO::getUpdateTime, timestamp);
        if (incrementMessageCount) {
            wrapper.set(SkillFactoryAuthoringSessionDO::getMessageCount,
                    defaultLong(current.getMessageCount()) + 1L);
        }
        if (StringUtils.isBlank(current.getTitle()) && StringUtils.isNotBlank(titleCandidate)) {
            wrapper.set(SkillFactoryAuthoringSessionDO::getTitle, abbreviate(titleCandidate));
        }
        sessionMapper.update(null, wrapper);
    }

    private AuthoringSession toDomain(SkillFactoryAuthoringSessionDO sessionDO) {
        return new AuthoringSession()
                .setSessionId(sessionDO.getSessionId())
                .setBizKey(sessionDO.getBizKey())
                .setScopeType(sessionDO.getScopeType())
                .setScopeId(sessionDO.getScopeId())
                .setWorkspaceId(sessionDO.getWorkspaceId())
                .setTitle(sessionDO.getTitle())
                .setCreator(sessionDO.getCreator())
                .setLastOperator(sessionDO.getLastOperator())
                .setActive(Integer.valueOf(ACTIVE).equals(sessionDO.getActive()))
                .setMessageCount(defaultLong(sessionDO.getMessageCount()))
                .setLastMessageTime(defaultLong(sessionDO.getLastMessageTime()))
                .setCreateTime(defaultLong(sessionDO.getCreateTime()))
                .setUpdateTime(defaultLong(sessionDO.getUpdateTime()));
    }

    private String newSessionId(AuthoringSessionScope scope) {
        String time = LocalDateTime.now().format(SESSION_TIME_FORMATTER);
        String random = UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        return SESSION_ID_PREFIX + safe(scope.getBizKey()) + "_" + safe(scope.getScopeType()) + "_"
                + safe(scope.getScopeId()) + "_" + time + "_" + random;
    }

    private String safe(String value) {
        String text = StringUtils.defaultIfBlank(value, UNKNOWN_SCOPE_VALUE);
        String safeText = text.replaceAll("[^A-Za-z0-9]", "_");
        return safeText.length() > 32 ? safeText.substring(0, 32) : safeText;
    }

    private String abbreviate(String value) {
        String text = StringUtils.defaultString(value).trim();
        return text.length() <= TITLE_MAX_LENGTH ? text : text.substring(0, TITLE_MAX_LENGTH) + "...";
    }

    private long defaultLong(Long value) {
        return value == null ? 0L : value;
    }
}
