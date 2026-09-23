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
import dev.a2flow.management.aicoding.SkillFactoryAiCodingService;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory AI Coding 的 patch 草稿工具。
 *
 * <p>模型只能通过该工具把文件变更写入 `_patches` 暂存区，并返回 patchId 和预览；
 * 操作者显式决定是否应用到正式 workspace。该工具不负责 lifecycle、包发布、
 * 组件中心或任意通用文件写入。
 */
@Slf4j
@Component
public class SkillFactoryProposePatchToolCallback implements ToolCallback {

    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_USER_NAME = "userName";

    private static final String FIELD_WORKSPACE_ROOT = "workspaceRoot";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_BIZ_KEY = "bizKey";

    private static final String TOOL_PROPOSE_PATCH = "propose_patch";
    private static final String TOOL_DESCRIPTION = "Create a SkillFactory patch proposal. This stores proposed file "
            + "changes in the patch staging area and returns a patchId. The user previews the changes and decides whether "
            + "the patch remains pending or is applied to workspace files.";

    private static final String INPUT_SCHEMA = """
            {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Short summary of the proposed Skill changes"},
                    "changedFiles": {
                        "type": "array",
                        "description": "Files to add, modify, or delete after the user explicitly applies the patch",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "Relative path inside the Skill workspace"},
                                "changeType": {"type": "string", "description": "ADD, MODIFY, or DELETE"},
                                "content": {"type": "string", "description": "Full target file content for ADD/MODIFY"}
                            },
                            "required": ["path", "changeType"]
                        }
                    },
                    "riskItems": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Business or frontend contract risks the operator should confirm"
                    }
                },
                "required": ["changedFiles"]
            }
            """;

    @Resource
    private SkillFactoryAiCodingService aiCodingService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_PROPOSE_PATCH)
                .description(TOOL_DESCRIPTION)
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /**
     * 执行模型发起的 propose_patch 工具调用。
     *
     * <p>该方法从 ToolContext 中读取 AI Coding chat 上下文，只把模型给出的
     * changedFiles 转成 patch 草稿；不会直接应用文件变更，也不会访问 SkillFactory
     * lifecycle 或组件中心能力。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        if (StringUtils.isBlank(toolInput) || Objects.isNull(toolContext)) {
            throw new ToolException("tool invalid params", ToolException.ErrorCode.INVALID_PARAMS);
        }
        Map<String, Object> toolContextMap = toolContext.getContext();
        BaseAgentContext agentContext = (BaseAgentContext) toolContextMap.get("agentContext");
        if (Objects.isNull(agentContext)) {
            throw new ToolException("agentContext not exists", ToolException.ErrorCode.PERMISSION_DENIED);
        }
        Map<String, Object> input = JsonSupport.fromJson(toolInput);
        Map<String, String> params = buildParams(agentContext);
        log.info("SkillFactory propose_patch工具开始执行, workspaceId={}, sessionId={}, inputKeys={}",
                params.get(FIELD_WORKSPACE_ID), params.get(FIELD_SESSION_ID), input.keySet());
        return aiCodingService.proposePatch(params, input);
    }

    private Map<String, String> buildParams(BaseAgentContext agentContext) {
        Map<String, Object> extraBizParam = Objects.isNull(agentContext.getExtraBizParam())
                                            ? Maps.newHashMap() : agentContext.getExtraBizParam();
        Map<String, String> params = Maps.newHashMap();
        putString(params, FIELD_WORKSPACE_ID, MapUtils.getString(extraBizParam, FIELD_WORKSPACE_ID));
        putString(params, FIELD_SKILL_CODE, MapUtils.getString(extraBizParam, FIELD_SKILL_CODE));
        putString(params, FIELD_BIZ_KEY, MapUtils.getString(extraBizParam, FIELD_BIZ_KEY));
        putString(params, FIELD_SESSION_ID, MapUtils.getString(extraBizParam, FIELD_SESSION_ID));
        putString(params, FIELD_USER_NAME,
                MapUtils.getString(extraBizParam, FIELD_USER_NAME,
                        dev.a2flow.management.access.UserIds.toWire(agentContext.getUserId())));

        putString(params, FIELD_WORKSPACE_ROOT, MapUtils.getString(extraBizParam, FIELD_WORKSPACE_ROOT));
        putString(params, FIELD_TRACE_ID, MapUtils.getString(extraBizParam, FIELD_TRACE_ID));
        putString(params, FIELD_RUN_ID, MapUtils.getString(extraBizParam, FIELD_RUN_ID));
        putString(params, FIELD_CONVERSATION_ID, MapUtils.getString(extraBizParam, FIELD_CONVERSATION_ID));
        putString(params, FIELD_MESSAGE, StringUtils.defaultIfBlank(
                MapUtils.getString(extraBizParam, FIELD_MESSAGE), agentContext.getUserMessage()));
        return params;
    }

    private void putString(Map<String, String> params, String key, String value) {
        if (StringUtils.isNotBlank(value)) {
            params.put(key, value);
        }
    }
}
