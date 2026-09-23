package dev.a2flow.management.aicoding.tool.skill;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.engine.model.BaseAgentContext;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;

/**
 * Skill 创建期依赖 Tool 的可信上下文辅助类。
 *
 * <p>它只从后端注入的 {@link BaseAgentContext} 读取 workspace、会话和审批字段，不接受模型在
 * Tool 参数中指定 workspaceId 或 skillCode，从而避免模型越权查询其他 Skill 的引用事实。
 */
public final class SkillFactoryDependencyToolSupport {

    private static final String FIELD_AGENT_CONTEXT = "agentContext";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final List<String> PATCH_CONTEXT_FIELDS = List.of(
            FIELD_WORKSPACE_ID, "skillCode", "bizKey", "sessionId", "userName",
            "workspaceRoot", "traceId", "runId",
            "conversationId", "messageId", "message");

    private SkillFactoryDependencyToolSupport() {
    }

    /**
     * 拒绝缺少可信 ToolContext 的直接调用。
     *
     * <p>依赖 Tool 必须从后端上下文解析当前 workspace，不能在缺少上下文时静默返回或接受模型
     * 补充 workspaceId。
     */
    public static String rejectUntrustedCall() {
        throw new ToolException("trusted toolContext is required",
                ToolException.ErrorCode.PERMISSION_DENIED);
    }

    static BaseAgentContext requireAgentContext(ToolContext toolContext) {
        if (toolContext == null || toolContext.getContext() == null) {
            throw new ToolException("toolContext not exists", ToolException.ErrorCode.PERMISSION_DENIED);
        }
        BaseAgentContext agentContext =
                (BaseAgentContext) toolContext.getContext().get(FIELD_AGENT_CONTEXT);
        if (agentContext == null) {
            throw new ToolException("agentContext not exists", ToolException.ErrorCode.PERMISSION_DENIED);
        }
        return agentContext;
    }

    public static String trustedWorkspaceId(ToolContext toolContext) {
        BaseAgentContext agentContext = requireAgentContext(toolContext);
        String workspaceId = MapUtils.getString(extraBizParam(agentContext), FIELD_WORKSPACE_ID);
        if (StringUtils.isBlank(workspaceId)) {
            throw new ToolException("trusted workspaceId is required", ToolException.ErrorCode.PERMISSION_DENIED);
        }
        return workspaceId;
    }

    public static Map<String, String> trustedPatchParams(ToolContext toolContext) {
        BaseAgentContext agentContext = requireAgentContext(toolContext);
        Map<String, Object> extraBizParam = extraBizParam(agentContext);
        Map<String, String> params = new LinkedHashMap<>();
        for (String field : PATCH_CONTEXT_FIELDS) {
            String value = MapUtils.getString(extraBizParam, field);
            if (StringUtils.isNotBlank(value)) {
                params.put(field, value);
            }
        }
        params.putIfAbsent("userName", dev.a2flow.management.access.UserIds.toWire(agentContext.getUserId()));
        params.putIfAbsent("message", agentContext.getUserMessage());
        return params;
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> parseObject(String toolInput, List<String> allowedFields) {
        if (StringUtils.isBlank(toolInput)) {
            return Collections.emptyMap();
        }
        try {
            Object parsed = JsonSupport.fromJSON(toolInput, Object.class);
            if (!(parsed instanceof Map<?, ?>)) {
                throw new IllegalArgumentException("tool input must be JSON object");
            }
            Map<String, Object> input = new LinkedHashMap<>((Map<String, Object>) parsed);
            if (!allowedFields.containsAll(input.keySet())) {
                throw new IllegalArgumentException("tool input contains unsupported fields");
            }
            return input;
        } catch (Exception e) {
            throw new ToolException("dependency tool input is invalid", e,
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
    }

    private static Map<String, Object> extraBizParam(BaseAgentContext agentContext) {
        return Objects.requireNonNullElse(agentContext.getExtraBizParam(), Collections.emptyMap());
    }
}
