package dev.a2flow.management.agentcore.runtime.tool;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import com.google.common.collect.Lists;
import dev.a2flow.management.support.DeploymentEnvironment;
import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineContext;

import lombok.extern.slf4j.Slf4j;

/**

 * Created on 2026-04-27
 */
@Slf4j
@Component
public class ToolManager {

    private final Map<String, ToolCallback> toolCallbackMap = new LinkedHashMap<>();

    public ToolManager(List<ToolCallback> toolCallbackList) {
        for (ToolCallback toolCallback : toolCallbackList) {
            ToolDefinition toolDefinition = toolCallback.getToolDefinition();
            if (toolCallbackMap.containsKey(toolDefinition.name())) {
                throw new RuntimeException(
                        "[ToolManager] 存在重复的toolCallback:" + toolDefinition.name());
            }
            toolCallbackMap.put(toolDefinition.name(), toolCallback);
            log.info("[ToolManager] init toolCallback, toolName:{}", toolDefinition.name());
        }
    }

    public List<ToolCallback> getToolCallByNames(List<String> toolNames, AgentEngineContext engineContext) {
        if (CollectionUtils.isEmpty(toolNames)) {
            return Lists.newArrayList();
        }
        toolNames = toolNames.stream().distinct().toList();
        if (!DeploymentEnvironment.isProd()) {
            log.info("ToolManager getToolCallByNames, toolNames:{}", toolNames);
        }
        List<ToolCallback> result = Lists.newArrayList();
        for (String toolName : toolNames) {
            ToolCallback toolCallback = toolCallbackMap.get(toolName);
            if (Objects.nonNull(toolCallback)) {
                result.add(toolCallback);
            }
        }
        return result;
    }

    public ToolCallback getToolCallback(String name) {
        if (StringUtils.isBlank(name)) {
            return null;
        }
        return MapUtils.getObject(toolCallbackMap, name);
    }
}
