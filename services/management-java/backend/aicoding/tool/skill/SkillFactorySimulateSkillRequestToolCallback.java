package dev.a2flow.management.aicoding.tool.skill;

import java.util.Map;
import java.util.Objects;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import com.google.common.collect.Maps;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.engine.model.BaseAgentContext;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;
import dev.a2flow.management.aicoding.validation.SkillFactorySimulateSkillRequestService;
import dev.a2flow.management.aicoding.validation.SkillSimulationResult;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 只读模拟 Skill 请求工具。
 *
 * <p>该工具供验证型 peer Agent 使用。它只能读取当前 Skill 工作区并返回模拟运行证据；
 * 没有真实 runtime adapter 时必须返回 PARTIAL/FAILED，不允许伪装 PASSED。
 */
@Slf4j
@Component
public class SkillFactorySimulateSkillRequestToolCallback implements ToolCallback {

    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_WORKSPACE_ROOT = "workspaceRoot";
    private static final String FIELD_TEST_INPUT = "testInput";
    private static final String FIELD_MESSAGE = "message";

    private static final String TOOL_DESCRIPTION = "Simulate a Skill request in read-only dry-run mode. This tool "
            + "must be called by validation Agents before returning a ValidationReport. It never writes workspace "
            + "files or creates patches.";

    private static final String INPUT_SCHEMA = """
            {
                "type": "object",
                "properties": {
                    "workspaceId": {"type": "string", "description": "Skill workspace identity"},
                    "skillCode": {"type": "string", "description": "Skill code"},
                    "testInput": {"type": "string", "description": "Input used to simulate the Skill request"}
                },
                "required": ["testInput"]
            }
            """;

    @Resource
    private SkillFactorySimulateSkillRequestService simulateSkillRequestService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(SkillSimulationResult.TOOL_NAME)
                .description(TOOL_DESCRIPTION)
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /**
     * 执行只读模拟请求。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        if (StringUtils.isBlank(toolInput) || Objects.isNull(toolContext)) {
            throw new ToolException("tool invalid params", ToolException.ErrorCode.INVALID_PARAMS);
        }
        Map<String, Object> contextMap = toolContext.getContext();
        BaseAgentContext agentContext = (BaseAgentContext) contextMap.get("agentContext");
        if (Objects.isNull(agentContext)) {
            throw new ToolException("agentContext not exists", ToolException.ErrorCode.PERMISSION_DENIED);
        }
        Map<String, Object> input = JsonSupport.fromJson(toolInput);
        Map<String, String> params = buildParams(agentContext, input);
        log.info("SkillFactory simulate_skill_request工具开始执行, workspaceId={}, skillCode={}, testInputLength={}",
                params.get(FIELD_WORKSPACE_ID), params.get(FIELD_SKILL_CODE),
                StringUtils.length(params.get(FIELD_TEST_INPUT)));
        return JsonSupport.toJSON(simulateSkillRequestService.simulate(params));
    }

    private Map<String, String> buildParams(BaseAgentContext agentContext, Map<String, Object> input) {
        Map<String, Object> extraBizParam = Objects.isNull(agentContext.getExtraBizParam())
                                            ? Maps.newHashMap() : agentContext.getExtraBizParam();
        Map<String, String> params = Maps.newHashMap();
        putString(params, FIELD_WORKSPACE_ID, StringUtils.defaultIfBlank(MapUtils.getString(input, FIELD_WORKSPACE_ID),
                MapUtils.getString(extraBizParam, FIELD_WORKSPACE_ID)));
        putString(params, FIELD_SKILL_CODE, StringUtils.defaultIfBlank(MapUtils.getString(input, FIELD_SKILL_CODE),
                MapUtils.getString(extraBizParam, FIELD_SKILL_CODE)));
        putString(params, FIELD_WORKSPACE_ROOT, MapUtils.getString(extraBizParam, FIELD_WORKSPACE_ROOT));
        putString(params, FIELD_TEST_INPUT, StringUtils.defaultIfBlank(MapUtils.getString(input, FIELD_TEST_INPUT),
                MapUtils.getString(extraBizParam, FIELD_MESSAGE, agentContext.getUserMessage())));
        putString(params, FIELD_MESSAGE, agentContext.getUserMessage());
        return params;
    }

    private void putString(Map<String, String> params, String key, String value) {
        if (StringUtils.isNotBlank(value)) {
            params.put(key, value);
        }
    }
}
