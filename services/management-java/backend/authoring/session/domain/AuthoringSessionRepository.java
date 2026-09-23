package dev.a2flow.management.authoring.session.domain;

import java.util.List;

/**
 * Authoring Chat 会话领域仓储。
 *
 * <p>应用服务只依赖该接口，不感知 MyBatis、DO 或具体表结构。该仓储只管理 session 身份、激活状态
 * 和最近沟通摘要；turn/event 的明细持久化由各自仓储负责。
 */
public interface AuthoringSessionRepository {

    /**
     * 确保指定会话存在并成为当前 scope 的活跃会话。
     */
    AuthoringSession ensureSession(AuthoringSessionScope scope, String sessionId);

    /**
     * 创建并激活新会话，保留当前 scope 的历史会话。
     */
    AuthoringSession createNewSession(AuthoringSessionScope scope);

    /**
     * 查询 scope 下的全部会话，按最近沟通时间倒序返回。
     */
    List<AuthoringSession> listSessions(AuthoringSessionScope scope);

    /**
     * 查询 scope 下的指定会话，不存在时返回 null。
     */
    AuthoringSession findSession(AuthoringSessionScope scope, String sessionId);

    /**
     * 用户 turn 成功写入后，更新会话标题、消息数和最近沟通时间。
     */
    void recordTurn(AuthoringSessionScope scope, String sessionId, long timestamp, String titleCandidate);

    /**
     * 完整 Assistant turn 成功写入后，更新会话最近沟通时间。
     */
    void recordAssistantTurn(AuthoringSessionScope scope, String sessionId, long timestamp);

    /**
     * 终态流式事件成功写入后，兜底更新会话最近活动时间。
     */
    void recordEvent(AuthoringSessionScope scope, String sessionId, long timestamp);
}
