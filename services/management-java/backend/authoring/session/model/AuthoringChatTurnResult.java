package dev.a2flow.management.authoring.session.model;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Authoring Chat 对话 turn 返回模型。
 *
 * <p>该模型用于页面恢复用户输入和后端欢迎消息，并保留持久化操作者供共享会话署名；operator 只用于
 * 展示和审计，不参与会话查询或权限判断。该模型不承载模型流式执行事件。
 */
@Data
@Accessors(chain = true)
public class AuthoringChatTurnResult {

    private String id;
    private String role;
    private String text;
    private long timestamp;
    private String sessionId;
    private String messageId;
    private String operator;
}
