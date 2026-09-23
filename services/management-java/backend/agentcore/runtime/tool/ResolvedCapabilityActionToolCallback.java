package dev.a2flow.management.agentcore.runtime.tool;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;

import dev.a2flow.management.model.CapabilityActionExecutionPlan;
import dev.a2flow.management.release.ReleaseEnvironment;

/**
 * 已解析发布源的单次业务能力执行回调。
 *
 * <p>本类只承接 Provider 已完成不可变快照解析后的执行计划和实际 resolvedEnvironment，随后调用
 * CapabilityActionExecutor。它不读取模型参数中的环境、不重新选择发布指针，也不会注册为全局 Tool。
 */
final class ResolvedCapabilityActionToolCallback implements ToolCallback {

    private final CapabilityActionExecutionPlan executionPlan;
    private final CapabilityActionExecutor capabilityActionExecutor;
    private final ReleaseEnvironment requestedEnvironment;
    private final ReleaseEnvironment resolvedEnvironment;
    private final ToolDefinition toolDefinition;

    ResolvedCapabilityActionToolCallback(CapabilityActionExecutionPlan executionPlan,
            CapabilityActionExecutor capabilityActionExecutor, ReleaseEnvironment requestedEnvironment,
            ReleaseEnvironment resolvedEnvironment) {
        this.executionPlan = executionPlan;
        this.capabilityActionExecutor = capabilityActionExecutor;
        this.requestedEnvironment = requestedEnvironment;
        this.resolvedEnvironment = resolvedEnvironment;
        this.toolDefinition = ToolDefinition.builder()
                .name(ExecuteBusinessCapabilityToolCallback.TOOL_NAME)
                .description(executionPlan.getToolDescription())
                .inputSchema(executionPlan.getInputSchema())
                .build();
    }

    @Override
    public ToolDefinition getToolDefinition() {
        return toolDefinition;
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /**
     * 按已解析的不可变执行计划和实际环境执行受控业务能力。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        return capabilityActionExecutor.execute(executionPlan, toolInput, toolContext,
                requestedEnvironment, resolvedEnvironment);
    }
}
