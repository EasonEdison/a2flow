package dev.a2flow.management.config;

import java.util.ArrayList;
import java.util.List;

import lombok.Data;

/**
 * SkillFactory 可被工具调用的平级 Agent 配置。
 *
 * <p>该模型只用于 `invoke_agent` 工具的后端白名单校验。它声明 Agent 身份、可承接任务类型、
 * 必须留下证据的工具、期望输出结构和只读/禁写等约束，不把某个 Agent 固定成永久子 Agent。
 */
@Data
public class SkillFactoryPeerAgentConfig {

    private String alias;
    private String bizKey;
    private String agentId;
    private String description;
    private List<String> taskTypes = new ArrayList<>();
    private List<String> requiredTools = new ArrayList<>();
    private String expectedOutputType;
    private boolean readOnly = true;
    private boolean noPatch = true;
    private boolean noWorkspaceWrite = true;
    private boolean noBusinessSideEffect = true;
    private long timeoutMs = 60000L;
}
