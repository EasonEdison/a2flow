package dev.a2flow.management.storage.db.repository;

import java.util.List;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Repository;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import dev.a2flow.management.authoring.session.domain.AuthoringChatTurn;
import dev.a2flow.management.authoring.session.domain.AuthoringChatTurnRepository;
import dev.a2flow.management.storage.db.entity.SkillFactoryAuthoringTurnDO;
import dev.a2flow.management.storage.db.mapper.SkillFactoryAuthoringTurnMapper;
import dev.a2flow.management.storage.db.mapper.SkillFactoryMapperConstants;

import lombok.extern.slf4j.Slf4j;

/**
 * Authoring Chat 对话 turn 仓储的 MySQL 实现。
 *
 * <p>该类只在 turn 领域对象与 turn DO 之间转换，不维护会话摘要，也不向应用层暴露 Mapper/DO。
 */
@Repository
@Slf4j
public class SkillFactoryAuthoringChatTurnDbRepository implements AuthoringChatTurnRepository {

    private static final int NOT_DELETED = 0;
    private static final String INSERT_FAILED_MESSAGE = "insert authoring turn failed";

    @Resource
    private SkillFactoryAuthoringTurnMapper turnMapper;

    /**
     * 幂等写入一条 turn。
     */
    @Override
    @org.springframework.transaction.annotation.Transactional(rollbackFor = Exception.class)
    public boolean append(AuthoringChatTurn turn) {
        if (turn == null || StringUtils.isAnyBlank(turn.getTurnId(), turn.getSessionId())) {
            return false;
        }
        if (exists(turn.getTurnId())) {
            log.info("SkillFactory Authoring Chat跳过重复turn, sessionId={}, turnId={}",
                    turn.getSessionId(), turn.getTurnId());
            return false;
        }
        long timestamp = turn.getTimestamp() > 0 ? turn.getTimestamp() : System.currentTimeMillis();
        SkillFactoryAuthoringTurnDO turnDO = new SkillFactoryAuthoringTurnDO()
                .setTurnId(turn.getTurnId())
                .setSessionId(turn.getSessionId())
                .setRole(turn.getRole())
                .setMessageId(turn.getMessageId())
                .setText(turn.getText())
                .setOperator(turn.getOperator())
                .setTimestamp(timestamp)
                .setDeleted(NOT_DELETED)
                .setCreateTime(timestamp)
                .setUpdateTime(timestamp);
        try {
            if (turnMapper.insert(turnDO) <= 0) {
                throw new IllegalStateException(INSERT_FAILED_MESSAGE);
            }
        } catch (DuplicateKeyException exception) {
            log.info("SkillFactory Authoring Chat并发写入重复turn，按幂等成功处理, sessionId={}, turnId={}",
                    turn.getSessionId(), turn.getTurnId());
            return false;
        }
        log.info("SkillFactory Authoring Chat turn已写入DB, sessionId={}, turnId={}, role={}",
                turn.getSessionId(), turn.getTurnId(), turn.getRole());
        return true;
    }

    /**
     * 按时间正序查询会话 turn。
     */
    @Override
    public List<AuthoringChatTurn> listBySessionId(String sessionId) {
        LambdaQueryWrapper<SkillFactoryAuthoringTurnDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryAuthoringTurnDO::getSessionId, sessionId)
                .eq(SkillFactoryAuthoringTurnDO::getDeleted, NOT_DELETED)
                .orderByAsc(SkillFactoryAuthoringTurnDO::getTimestamp)
                .orderByAsc(SkillFactoryAuthoringTurnDO::getId);
        return turnMapper.selectList(wrapper).stream().map(this::toDomain).collect(Collectors.toList());
    }

    private boolean exists(String turnId) {
        LambdaQueryWrapper<SkillFactoryAuthoringTurnDO> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SkillFactoryAuthoringTurnDO::getTurnId, turnId)
                .eq(SkillFactoryAuthoringTurnDO::getDeleted, NOT_DELETED);
        return turnMapper.selectCount(wrapper) > 0;
    }

    private AuthoringChatTurn toDomain(SkillFactoryAuthoringTurnDO turnDO) {
        return new AuthoringChatTurn()
                .setTurnId(turnDO.getTurnId())
                .setSessionId(turnDO.getSessionId())
                .setRole(turnDO.getRole())
                .setMessageId(turnDO.getMessageId())
                .setText(turnDO.getText())
                .setOperator(turnDO.getOperator())
                .setTimestamp(defaultLong(turnDO.getTimestamp()));
    }

    private long defaultLong(Long value) {
        return value == null ? 0L : value;
    }
}
