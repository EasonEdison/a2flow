package dev.a2flow.management.aicoding.validation;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory peer Agent 单次执行结果。
 *
 * <p>该对象只记录 `invoke_agent` 发起的一次平级 Agent 调用证据。它不代表长期主子关系，
 * 也不持久化 Agent 编排拓扑，只服务当前主 Agent 对工具型 peer Agent 返回值的结构化消费。
 */
@Data
@Accessors(chain = true)
public class SkillFactoryPeerAgentRunResult {

    private String childSessionId;
    private String childRunId;
    private String calleeAlias;
    private String calleeBizKey;
    private String calleeAgentId;
    private String taskType;
    private String expectedOutputType;
    private boolean completed;
    private boolean simulateToolCalled;
    private boolean simulateToolSucceeded;
    private String errorMessage;
    private String finalAnswer;
    private long costMs;
    private SkillSimulationResult simulationResult;
    private List<Map<String, Object>> childEventSummary = new ArrayList<>();
    private List<Map<String, Object>> requiredToolEvidence = new ArrayList<>();
}
