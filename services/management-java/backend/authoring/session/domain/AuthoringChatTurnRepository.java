package dev.a2flow.management.authoring.session.domain;

import java.util.List;

/**
 * Authoring Chat 对话 turn 领域仓储。
 *
 * <p>该接口只负责用户/助手 turn 的幂等持久化与会话内顺序查询，不维护 session 摘要，也不感知
 * MyBatis、DO 或页面 DTO。
 */
public interface AuthoringChatTurnRepository {

    /**
     * 幂等写入 turn；实际插入返回 true，重复 turn 返回 false。
     */
    boolean append(AuthoringChatTurn turn);

    /**
     * 按时间正序查询指定会话的全部 turn。
     */
    List<AuthoringChatTurn> listBySessionId(String sessionId);
}
