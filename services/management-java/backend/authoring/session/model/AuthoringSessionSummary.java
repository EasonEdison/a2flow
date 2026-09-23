package dev.a2flow.management.authoring.session.model;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Authoring Chat 会话摘要返回模型。
 *
 * <p>该模型只承载会话下拉需要的稳定字段，包括用于识别共享会话的创建人和最近操作者；这些字段只做
 * 展示和审计，不参与 scope 查询或权限判断。该模型不暴露数据库主键、逻辑删除等持久化细节。
 */
@Data
@Accessors(chain = true)
public class AuthoringSessionSummary {

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
