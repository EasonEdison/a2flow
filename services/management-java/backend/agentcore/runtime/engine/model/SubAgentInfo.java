package dev.a2flow.management.agentcore.runtime.engine.model;

import java.util.List;

import lombok.Data;

/**

 * Created on 2026-04-24
 */
@Data
public class SubAgentInfo {
    private long agentId;
    private String agentName;
    private String hitRangeDesc;
    private String bizRolePrompt;
    private String engineStrategy;
    private List<String> skillList;
}
