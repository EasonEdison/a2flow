package dev.a2flow.management.authoring.session.domain;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Authoring Chat 对话 turn 领域对象。
 *
 * <p>用户输入和聚合后的完整 Assistant 回复使用 turn 表达；模型流式 delta 只实时传输，
 * 工具、Patch、审批和终态等结构化过程使用独立事件表达。该对象只保存可回放的角色、文本和消息身份，
 * 不承载模型执行过程或数据库行字段。
 */
@Data
@Accessors(chain = true)
public class AuthoringChatTurn {

    private String turnId;
    private String sessionId;
    private String role;
    private String messageId;
    private String text;
    private String operator;
    private long timestamp;
}
