package dev.a2flow.management.aicoding.engine;

import java.util.Collections;
import java.util.List;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.messages.AssistantMessage;

import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineResult;

/**
 * 单次 AI Coding ReAct 执行内的模型 Tool 参数修复状态，不跨会话持久化。
 */
final class AiCodingMalformedToolRepairState {
    private final int maxRepairGenerations;
    private boolean repairing;
    private int repairGenerations;
    private String lastFinishReason = StringUtils.EMPTY;

    AiCodingMalformedToolRepairState(int maxRepairGenerations) {
        this.maxRepairGenerations = maxRepairGenerations;
    }

    boolean isRepairing() {
        return repairing;
    }

    int getRepairGenerations() {
        return repairGenerations;
    }

    String getLastFinishReason() {
        return lastFinishReason;
    }

    void recordFinishReason(String finishReason) {
        if (StringUtils.isNotBlank(finishReason)) {
            lastFinishReason = finishReason;
        }
    }

    boolean recordMalformedGeneration() {
        if (repairing) {
            return recordRepairGeneration();
        }
        repairing = true;
        repairGenerations = 0;
        return false;
    }

    boolean recordRepairGeneration() {
        repairGenerations++;
        return repairGenerations >= maxRepairGenerations;
    }

    void reset() {
        repairing = false;
        repairGenerations = 0;
        lastFinishReason = StringUtils.EMPTY;
    }
}

/**
 * 参数修复阶段完成去重后的 Tool 执行选择结果。
 */
final class AiCodingToolRepairSelection {
    private final List<AssistantMessage.ToolCall> executableToolCalls;
    private final boolean assistantMessageAdded;
    private final AgentEngineResult terminalResult;

    private AiCodingToolRepairSelection(List<AssistantMessage.ToolCall> executableToolCalls,
            boolean assistantMessageAdded, AgentEngineResult terminalResult) {
        this.executableToolCalls = executableToolCalls;
        this.assistantMessageAdded = assistantMessageAdded;
        this.terminalResult = terminalResult;
    }

    static AiCodingToolRepairSelection execute(List<AssistantMessage.ToolCall> toolCalls,
            boolean assistantMessageAdded) {
        return new AiCodingToolRepairSelection(toolCalls, assistantMessageAdded, null);
    }

    static AiCodingToolRepairSelection waitForRepair() {
        return new AiCodingToolRepairSelection(Collections.emptyList(), true, null);
    }

    static AiCodingToolRepairSelection terminal(AgentEngineResult terminalResult) {
        return new AiCodingToolRepairSelection(Collections.emptyList(), true, terminalResult);
    }

    List<AssistantMessage.ToolCall> getExecutableToolCalls() {
        return executableToolCalls;
    }

    boolean isAssistantMessageAdded() {
        return assistantMessageAdded;
    }

    AgentEngineResult getTerminalResult() {
        return terminalResult;
    }
}
