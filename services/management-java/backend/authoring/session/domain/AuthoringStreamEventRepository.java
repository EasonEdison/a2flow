package dev.a2flow.management.authoring.session.domain;

import java.util.List;

/**
 * Authoring Chat 结构化流式事件领域仓储。
 *
 * <p>该接口只负责运行事件的幂等持久化与会话内顺序查询。事件协议字段通过领域对象表达，应用层不接触
 * 数据库行对象。
 */
public interface AuthoringStreamEventRepository {

    /**
     * 幂等写入事件；实际插入返回 true，重复事件返回 false。
     */
    boolean append(AuthoringStreamEvent event);

    /**
     * 按时间正序查询指定会话的全部流式事件。
     */
    List<AuthoringStreamEvent> listBySessionId(String sessionId);

    /**
     * 按时间正序查询指定运行的全部公开流式事件。
     */
    List<AuthoringStreamEvent> listByRun(String sessionId, String invokeId);
}
