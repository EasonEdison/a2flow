package dev.a2flow.management.aicoding.tool.common;

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
import dev.a2flow.management.aicoding.validation.SkillFactoryPeerAgentInvocationService;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory peer Agent 调用工具。
 *
 * <p>模型通过该工具把某个平级 Agent 当成一次性工具型执行者调用。工具只按 SkillFactory KConf
 * 白名单执行授权任务，并把结构化结果返回当前 chat；它不引入新的后端 action 分流策略。
 */
@Slf4j
@Component
public class SkillFactoryInvokeAgentToolCallback implements ToolCallback {

    private static final String TOOL_INVOKE_AGENT = "invoke_agent";
    private static final String FIELD_BIZ_KEY = "bizKey";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_WORKSPACE_ROOT = "workspaceRoot";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String FIELD_REFERENCE_RENDER_ASSETS = "referenceRenderAssets";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_OWNER_ID = "ownerId";
    private static final String FIELD_USER_ID = "userId";
    private static final String FIELD_CLIENT = "client";

    private static final String TOOL_DESCRIPTION = "Invoke a configured peer Agent as a tool. Use this when the "
            + "user asks for runtime validation or another delegated task that should be handled by a configured "
            + "Agent. The backend validates alias/bizKey/agentId, taskType, required tools and expected output.";

    private static final String INPUT_SCHEMA = """
            {
                "type": "object",
                "properties": {
                    "alias": {"type": "string", "description": "Configured peer Agent alias, for example checkAgent"},
                    "bizKey": {"type": "string", "description": "Configured peer Agent bizKey"},
                    "agentId": {"type": "string", "description": "Configured peer Agent id"},
                    "taskType": {"type": "string", "description": "Delegated task type, for example SKILL_RUNTIME_VALIDATION"},
                    "expectedOutputType": {"type": "string", "description": "Expected structured output type"},
                    "message": {"type": "string", "description": "Natural-language task instruction for the peer Agent"},
                    "workspaceId": {"type": "string", "description": "Skill workspace identity"},
                    "skillCode": {"type": "string", "description": "Skill code"},
                    "testInput": {"type": "string", "description": "User input used by validation tasks"},
                    "referenceRenderAssets": {"type": "array", "description": "Reference render assets for validation"}
                },
                "required": ["taskType"]
            }
            """;

    @Resource
    private SkillFactoryPeerAgentInvocationService peerAgentInvocationService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_INVOKE_AGENT)
                .description(TOOL_DESCRIPTION)
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /**
     * 执行 peer Agent 工具调用。
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
        Map<String, String> params = buildParams(agentContext);
        log.info("SkillFactory invoke_agent工具开始执行, bizKey={}, workspaceId={}, inputKeys={}",
                params.get(FIELD_BIZ_KEY), params.get(FIELD_WORKSPACE_ID), input.keySet());
        return peerAgentInvocationService.invoke(params, input);
    }

    private Map<String, String> buildParams(BaseAgentContext agentContext) {
        Map<String, Object> extraBizParam = Objects.isNull(agentContext.getExtraBizParam())
                                            ? Maps.newHashMap() : agentContext.getExtraBizParam();
        Map<String, String> params = Maps.newHashMap();
        putString(params, FIELD_BIZ_KEY, MapUtils.getString(extraBizParam, FIELD_BIZ_KEY));
        putString(params, FIELD_WORKSPACE_ID, MapUtils.getString(extraBizParam, FIELD_WORKSPACE_ID));
        putString(params, FIELD_SKILL_CODE, MapUtils.getString(extraBizParam, FIELD_SKILL_CODE));
        putString(params, FIELD_WORKSPACE_ROOT, MapUtils.getString(extraBizParam, FIELD_WORKSPACE_ROOT));
        putString(params, FIELD_SESSION_ID, MapUtils.getString(extraBizParam, FIELD_SESSION_ID));
        putString(params, FIELD_MESSAGE_ID, MapUtils.getString(extraBizParam, FIELD_MESSAGE_ID));
        putString(params, FIELD_RUN_ID, MapUtils.getString(extraBizParam, FIELD_RUN_ID));
        putString(params, FIELD_CONVERSATION_ID, MapUtils.getString(extraBizParam, FIELD_CONVERSATION_ID));
        putString(params, FIELD_TRACE_ID, MapUtils.getString(extraBizParam, FIELD_TRACE_ID));
        putString(params, FIELD_REFERENCE_RENDER_ASSETS,
                MapUtils.getString(extraBizParam, FIELD_REFERENCE_RENDER_ASSETS));
        putString(params, FIELD_MESSAGE, agentContext.getUserMessage());
        putString(params, FIELD_OWNER_ID, agentContext.getOwnerId());
        putString(params, FIELD_USER_ID, dev.a2flow.management.access.UserIds.toWire(agentContext.getUserId()));
        putString(params, FIELD_CLIENT, agentContext.getClient());
        return params;
    }

    private void putString(Map<String, String> params, String key, String value) {
        if (StringUtils.isNotBlank(value)) {
            params.put(key, value);
        }
    }
}
