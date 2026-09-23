package dev.a2flow.management.agentcore.runtime.tool;

import java.util.Map;
import java.util.Objects;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.DeploymentEnvironment;
import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineContext;
import dev.a2flow.management.agentcore.runtime.tool.model.ToolResult;

import lombok.extern.slf4j.Slf4j;

/**
 * Agent-core 工具执行入口。
 *
 * <p>上游 Engine 提供模型生成的工具参数和普通业务上下文，本类从 {@link AgentEngineContext} 补充
 * 后端可信上下文后再调用 ToolCallback。它不修改 Tool schema、不把可信字段并入模型参数，也不负责
 * capability 或未来 orchestration 的领域校验。
 *

 * Created on 2026-04-25
 */
@Component
@Slf4j
public class ToolExecutor {

    @Resource
    private ToolManager toolManager;

    /**
     * 使用 Agent 本轮可信上下文执行指定 Tool，并返回统一的执行结果。
     */
    public ToolResult executeTool(AgentEngineContext engineContext, String toolName, String argsJson,
            Map<String, Object> bizToolContext) {
        ToolResult toolResult = executeToolRuntime(engineContext, toolName, argsJson, bizToolContext);
        return toolResult;
    }

    /**
     * 合并可信上下文后调用 ToolCallback；异常仅转换为 ToolResult，不改变模型参数或 Tool 定义。
     */
    public ToolResult executeToolRuntime(AgentEngineContext engineContext, String toolName, String argsJson,
            Map<String, Object> bizToolContext) {
        String bizKey = engineContext == null ? StringUtils.EMPTY : engineContext.getBizKey();
        String invokeId = engineContext == null ? StringUtils.EMPTY : engineContext.getInvokeId();
        try {
            Map<String, Object> trustedToolContext = TrustedToolContext.build(engineContext, bizToolContext);
            if (!DeploymentEnvironment.isProd()) {
                log.info("ToolExecutor开始执行工具, bizKey={}, invokeId={}, toolName={}, argsLength={}, "
                                + "contextKeys={}",
                        bizKey, invokeId, toolName, StringUtils.length(argsJson), trustedToolContext.keySet());
            }
            ToolCallback toolCallback = toolManager.getToolCallback(toolName);
            if (Objects.isNull(toolCallback)) {
                log.error("ToolExecutor未找到工具, bizKey={}, invokeId={}, toolName={}", bizKey, invokeId,
                        toolName);
                return ToolResult.failure("Tool execution failed: tool does not exist or has no permissions");
            }
            ToolContext toolContext = new ToolContext(trustedToolContext);
            long startTime = System.currentTimeMillis();
            String toolResult = toolCallback.call(argsJson, toolContext);
            long endTime = System.currentTimeMillis();
            return ToolResult.success(toolResult, endTime - startTime, StringUtils.length(toolResult));
        } catch (ToolException toolException) {
            log.error("ToolExecutor执行工具失败, bizKey={}, invokeId={}, toolName={}, argsLength={}",
                    bizKey, invokeId, toolName, StringUtils.length(argsJson), toolException);
            return ToolResult.failure("Tool execution failed: " + toolException.getMessage());
        } catch (Exception e) {
            log.error("ToolExecutor执行工具异常, bizKey={}, invokeId={}, toolName={}, argsLength={}",
                    bizKey, invokeId, toolName, StringUtils.length(argsJson), e);
            return ToolResult.failure("Tool execution failed: " + e.getMessage());
        }
    }

}
