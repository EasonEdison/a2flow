package dev.a2flow.management.authoring.session.domain;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Authoring Chat 会话领域对象。
 *
 * <p>该对象表达一个创作会话的身份、归属范围和最近沟通状态。它不包含 MyBatis 注解，也不暴露
 * 数据库主键，Repository 负责在该对象与会话 DO 之间转换；应用层再把它转换为页面所需摘要。
 */
@Data
@Accessors(chain = true)
public class AuthoringSession {

    private String sessionId;
    private String bizKey;
    private String scopeType;
    private String scopeId;
    private String workspaceId;
    private String title;
    private String creator;
    private String lastOperator;
    private boolean active;
    private long createTime;
    private long updateTime;
    private long lastMessageTime;
    private long messageCount;
}
