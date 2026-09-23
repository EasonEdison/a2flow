package dev.a2flow.management.config;

import java.util.ArrayList;
import java.util.List;

import lombok.Data;

/**
 * SkillFactory peer Agent 调用配置。
 *
 * <p>该配置描述当前 bizKey 是否允许通过 `invoke_agent` 工具调用其它平级 Agent，以及可调用 Agent
 * 的白名单、任务类型和安全约束。调用方和被调用方都是平级 Agent；只有本次工具调用期间才形成
 * 主 Agent / 子 Agent 的任务关系。
 */
@Data
public class SkillFactoryInvokeAgentConfig {

    private boolean enabled;
    private List<SkillFactoryPeerAgentConfig> allowedAgents = new ArrayList<>();
}
