package dev.a2flow.management.authoring.session.model;

import java.util.List;

import dev.a2flow.management.config.AuthoringGuideConfig;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Authoring Chat 历史查询返回模型。
 *
 * <p>该模型同时返回 scope 下按最近沟通时间倒排的会话摘要，以及当前选中会话的 turn/event
 * 时间线。Repository 返回领域聚合，应用服务负责转换并装配 Agent 引导配置。
 */
@Data
@Accessors(chain = true)
public class AuthoringSessionHistory {

    private String bizKey;
    private String scopeType;
    private String scopeId;
    private String workspaceId;
    private String activeSessionId;
    private String selectedSessionId;
    private List<AuthoringSessionSummary> sessions;
    private List<AuthoringChatTurnResult> turns;
    private List<AuthoringStreamEventResult> events;
    private AuthoringGuideConfig authoringGuideConfig;
}
