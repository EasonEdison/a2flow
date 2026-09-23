package dev.a2flow.management.aicoding.tool.common;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.engine.model.BaseAgentContext;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;
import dev.a2flow.management.authoring.form.AuthoringFormPatchService;
import dev.a2flow.management.event.AiCodingEventPayload;
import dev.a2flow.management.event.AiCodingEventPayloadCodec;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 通用表单修改提案 Tool。
 *
 * <p>模型只提供 operations 和摘要；formKey、entityId、revision、currentDraft 及链路身份均从
 * 可信 ToolContext 注入。下游返回 FORM_PATCH_PROPOSED 供前端人工审阅，本 Tool 不保存表单、
 * 不写 DB、不修改 Skill workspace，也不执行预览或发布。
 */
@Component
@Slf4j
public class SkillFactoryProposeFormPatchToolCallback implements ToolCallback {

    private static final String FIELD_AGENT_CONTEXT = "agentContext";
    private static final String FIELD_AUTHORING_DOMAIN = "authoringDomain";
    private static final String FIELD_FORM_KEY = "formKey";
    private static final String FIELD_ENTITY_ID = "entityId";
    private static final String FIELD_REVISION = "revision";
    private static final String FIELD_CURRENT_DRAFT = "currentDraft";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String ERROR_TOOL_CONTEXT_MISSING = "toolContext not exists";
    private static final String ERROR_AGENT_CONTEXT_MISSING = "agentContext not exists";
    private static final String ERROR_TOOL_INPUT_INVALID = "toolInput 必须是合法 JSON 对象";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "operations": {
                  "type": "array",
                  "description": "对当前表单提出的 RFC 6902 子集修改，只允许 add、replace、remove",
                  "items": {
                    "type": "object",
                    "properties": {
                      "op": {"type": "string", "enum": ["add", "replace", "remove"]},
                      "path": {"type": "string", "description": "当前 formKey 注册表内的 JSON Pointer"},
                      "value": {"description": "add/replace 的目标值"}
                    },
                    "required": ["op", "path"]
                  }
                },
                "summary": {"type": "string", "description": "给操作者看的本次修改摘要"}
              },
              "required": ["operations"]
            }
            """;

    @Resource
    private AuthoringFormPatchService authoringFormPatchService;

    @Resource
    private AiCodingEventPayloadCodec aiCodingEventPayloadCodec;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(AuthoringFormPatchService.TOOL_PROPOSE_FORM_PATCH)
                .description("Propose reviewable changes for the active SkillFactory form. "
                        + "Identity, revision and form schema come from trusted runtime context. "
                        + "This tool never persists form data; the operator must review and apply changes locally.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        throw new ToolException(ERROR_TOOL_CONTEXT_MISSING, ToolException.ErrorCode.PERMISSION_DENIED);
    }

    /**
     * 执行模型表单修改提案并返回标准 runtime payload JSON。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        BaseAgentContext agentContext = requireAgentContext(toolContext);
        Map<String, String> context = buildContext(agentContext);
        try {
            Map<String, Object> input = parseInput(toolInput);
            log.info("Authoring通用表单修改Tool开始执行, authoringDomain={}, formKey={}, entityId={}, "
                            + "revision={}, sessionId={}",
                    context.get(FIELD_AUTHORING_DOMAIN), context.get(FIELD_FORM_KEY),
                    context.get(FIELD_ENTITY_ID), context.get(FIELD_REVISION), context.get(FIELD_SESSION_ID));
            AiCodingEventPayload payload = authoringFormPatchService.propose(context, input);
            return aiCodingEventPayloadCodec.toJson(payload);
        } catch (IllegalArgumentException e) {
            log.warn("Authoring通用表单修改Tool参数校验失败, authoringDomain={}, formKey={}, entityId={}, "
                            + "revision={}, traceId={}, error={}",
                    context.get(FIELD_AUTHORING_DOMAIN), context.get(FIELD_FORM_KEY),
                    context.get(FIELD_ENTITY_ID), context.get(FIELD_REVISION), context.get(FIELD_TRACE_ID),
                    e.getMessage());
            throw new ToolException(e.getMessage(), e, ToolException.ErrorCode.INVALID_PARAMS);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseInput(String toolInput) {
        try {
            Map<String, Object> input = JsonSupport.fromJson(toolInput);
            if (input == null) {
                throw new IllegalArgumentException(ERROR_TOOL_INPUT_INVALID);
            }
            return input;
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException(ERROR_TOOL_INPUT_INVALID, e);
        }
    }

    private BaseAgentContext requireAgentContext(ToolContext toolContext) {
        if (Objects.isNull(toolContext)) {
            throw new ToolException(ERROR_TOOL_CONTEXT_MISSING, ToolException.ErrorCode.PERMISSION_DENIED);
        }
        BaseAgentContext agentContext = (BaseAgentContext) toolContext.getContext().get(FIELD_AGENT_CONTEXT);
        if (Objects.isNull(agentContext)) {
            throw new ToolException(ERROR_AGENT_CONTEXT_MISSING, ToolException.ErrorCode.PERMISSION_DENIED);
        }
        return agentContext;
    }

    private Map<String, String> buildContext(BaseAgentContext agentContext) {
        Map<String, Object> extraBizParam = agentContext.getExtraBizParam() == null
                                            ? Collections.emptyMap() : agentContext.getExtraBizParam();
        Map<String, String> context = new LinkedHashMap<>();
        putString(context, extraBizParam, FIELD_AUTHORING_DOMAIN);
        putString(context, extraBizParam, FIELD_FORM_KEY);
        putString(context, extraBizParam, FIELD_ENTITY_ID);
        putString(context, extraBizParam, FIELD_REVISION);
        putJson(context, extraBizParam, FIELD_CURRENT_DRAFT);
        putString(context, extraBizParam, FIELD_WORKSPACE_ID);
        putString(context, extraBizParam, FIELD_SESSION_ID);
        putString(context, extraBizParam, FIELD_MESSAGE_ID);
        putString(context, extraBizParam, FIELD_RUN_ID);
        putString(context, extraBizParam, FIELD_CONVERSATION_ID);
        putString(context, extraBizParam, FIELD_TRACE_ID);
        return context;
    }

    private void putString(Map<String, String> target, Map<String, Object> source, String field) {
        String value = MapUtils.getString(source, field);
        if (StringUtils.isNotBlank(value)) {
            target.put(field, value);
        }
    }

    private void putJson(Map<String, String> target, Map<String, Object> source, String field) {
        Object value = source.get(field);
        if (value == null) {
            return;
        }
        target.put(field, value instanceof String ? String.valueOf(value) : JsonSupport.toJSON(value));
    }
}
