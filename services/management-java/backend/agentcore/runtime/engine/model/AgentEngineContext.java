package dev.a2flow.management.agentcore.runtime.engine.model;

import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import dev.a2flow.management.agentcore.infrastructrue.kconf.model.AgentMemoryConfig;
import dev.a2flow.management.agentcore.infrastructrue.kconf.model.AgentPropertiesConfig;
import dev.a2flow.management.agentcore.infrastructrue.kconf.model.LLMModelConfig;
import dev.a2flow.management.protobuf.RecallKnowledgeParam;

import lombok.Data;

/**
 * SkillFactory Agent 单次执行上下文。
 *
 * <p>上游运行时在启动 Engine 前组装 Agent、会话、模型、记忆和可信业务上下文；下游 Engine、Tool
 * 与子 Agent 在本轮执行中共享这些数据。取消状态只在当前 run 内存中缓存，跨实例信号由运行控制服务
 * 写入 Redis，持久化开始/终态仍由 Authoring 事件负责。
 *

 * Created on 2026-04-23
 */
@Data
public class AgentEngineContext {
    private String bizKey;
    private long agentId;
    private String agentName;
    private String ownerId;               // Agent的Owner
    @com.fasterxml.jackson.databind.annotation.JsonSerialize(using = com.fasterxml.jackson.databind.ser.std.ToStringSerializer.class)
    private Long userId;
    private String bizRolePrompt;
    private String conversationId;
    private List<SubAgentInfo> subAgentInfoList;
    // agent执行时, 需要注入至TOOL/SKILL的基础上下文
    private BaseAgentContext agentContext;
    private String primaryConversationId;
    private AgentPropertiesConfig agentPropertiesConfig;
    private LLMModelConfig llmModelConfig;
    private AgentMemoryConfig agentMemoryConfig;
    private List<String> skillList;
    private String invokeId;
    private String traceId;
    // 由可信 Agent 宿主按有效 Skill 环境写入，仅通过 ToolContext 下发，禁止来自模型参数或外部 Chat。
    private String releaseEnvironment;
    // 当前有效 Skill 允许调用的 actionCode -> 稳定能力 assetKey，由宿主解析绑定关系后写入。
    private Map<String, String> businessCapabilityAssetKeys;
    private Map<Long, RecallKnowledgeParam> recallKnowledgeParamMap; // 用于主子Agent改写使用
    private RecallKnowledgeParam recallKnowledgeParam;
    private SubAgentInfo matchedSubAgent;
    private AtomicBoolean firstHandoverFlag = new AtomicBoolean(false);
    // Stop 已请求；同实例直接置位，跨实例由 Engine 检查点从 Redis 桥接。
    private AtomicBoolean cancellationRequested = new AtomicBoolean(false);
    // Engine 已在模型、工具或进程检查点观测到取消，只有该状态允许生成 RUN_CANCELLED。
    private AtomicBoolean cancellationObserved = new AtomicBoolean(false);
}
