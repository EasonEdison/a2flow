package dev.a2flow.management.agentcore.domain;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.agentcore.entity.Session;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 迁移后的轻量会话服务。
 *
 * <p>该类只承接 AI Coding 流式入口的 session 存取，当前使用进程内 Map 保障迁移后链路可运行。
 * 上游是 {@code SkillFactoryChatRuntimeService}，下游暂不访问原 agent-service session 表；
 * 后续如果需要跨实例恢复，再在该类背后切到 sellerdata 自己的 Repository/DB。它不负责普通数字员工
 * 会话分页、历史消息存储或会话管理接口。
 */
@Slf4j
@Service
public class SessionService {

    private static final Map<String, Session> SESSION_BY_ID = new ConcurrentHashMap<>();

    /**
     * 创建或覆盖当前 AI Coding session。
     */
    public Long create(Session session) {
        if (session == null || StringUtils.isBlank(session.getSessionId())) {
            return 0L;
        }
        SESSION_BY_ID.put(session.getSessionId(), session);
        log.info("SkillFactory本地会话已登记, agentId={}, userId={}, sessionId={}",
                session.getAgentId(), session.getUserId(), session.getSessionId());
        return 1L;
    }

    /**
     * 根据业务 sessionId 查询当前进程内会话。
     */
    public Session queryBySessionId(String sessionId) {
        if (StringUtils.isBlank(sessionId)) {
            return null;
        }
        return SESSION_BY_ID.get(sessionId);
    }
}
