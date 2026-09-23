package dev.a2flow.management.agentcore.entity;

import java.util.List;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Agent 实体

 * @date 2026/4/27
 */
@Data
@Accessors(chain = true)
public class Agent {

    /**
     * 业务标识
     */
    private Long agentId;
    /**
     * 业务标识
     */
    private String bizKey;

    /**
     * 用户ID
     */
    private String ownerId;

    /**
     * Agent名称
     */
    private String agentName;

    /**
     * Agent描述
     */
    private String description;

    /**
     * 父AgentID，0表示根节点，
     */
    private Long  parentId;

    /**
     * 系统提示词/人设
     */

    private String systemPrompt;
    /**
     * 技能列表
     */
    private List<String> skills;



}
