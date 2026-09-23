package dev.a2flow.management.config;

import lombok.Data;

/**
 * SkillFactory Agent 工具扩展配置。
 *
 * <p>该配置挂在 `skillFactoryAgentBizSummaryMapConfig.*.propertiesConfig.agentToolConfig`
 * 下，只控制 SkillFactory 可迁移包内的扩展工具，例如 peer Agent 调用。它不修改公共 Agent 配置模型，
 * 也不影响普通数字员工 ReActEngine 的工具白名单。
 */
@Data
public class SkillFactoryAgentToolConfig {

    private SkillFactoryInvokeAgentConfig invokeAgent = new SkillFactoryInvokeAgentConfig();
}
