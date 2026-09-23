package dev.a2flow.management.authoring.session.domain;

import java.util.List;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Authoring Chat 会话历史领域聚合。
 *
 * <p>应用服务从 session、turn、event 三个领域仓储组装该聚合，再转换为页面 DTO。它不包含页面引导
 * 配置；欢迎语和快捷入口由应用服务在返回 DTO 时装配。
 */
@Data
@Accessors(chain = true)
public class AuthoringSessionArchive {

    private AuthoringSessionScope scope;
    private String activeSessionId;
    private String selectedSessionId;
    private List<AuthoringSession> sessions;
    private List<AuthoringChatTurn> turns;
    private List<AuthoringStreamEvent> events;
}
