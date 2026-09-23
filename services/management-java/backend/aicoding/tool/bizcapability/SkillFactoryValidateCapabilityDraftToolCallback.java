package dev.a2flow.management.aicoding.tool.bizcapability;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
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
import dev.a2flow.management.event.AiCodingEventPayloadCodec;
import dev.a2flow.management.lifecycle.AuthoringDraftChangeService;

import lombok.extern.slf4j.Slf4j;

/**
 * 能力中心当前表单的只读静态校验 Tool。
 *
 * <p>该 Tool 从可信上下文读取 currentDraft 和 revision，复用 CapabilityActionDraftService 的
 * 结构校验并输出 `CAPABILITY_VALIDATION_REPORT`。它不会保存草稿、增加 revision，也不会把静态校验
 * 伪装成 API dry-run 或发布 READY 证据。
 */
@Component
@Slf4j
public class SkillFactoryValidateCapabilityDraftToolCallback implements ToolCallback {

    private static final String FIELD_AGENT_CONTEXT = "agentContext";
    private static final String FIELD_AUTHORING_DOMAIN = "authoringDomain";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_REVISION = "revision";
    private static final String FIELD_CURRENT_DRAFT = "currentDraft";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final List<String> CONTEXT_FIELDS = List.of(
            FIELD_AUTHORING_DOMAIN, FIELD_DRAFT_ID, FIELD_REVISION, FIELD_WORKSPACE_ID, FIELD_SESSION_ID,
            FIELD_MESSAGE_ID, FIELD_RUN_ID, FIELD_CONVERSATION_ID, FIELD_TRACE_ID);
    private static final String ERROR_TOOL_CONTEXT_MISSING = "toolContext not exists";
    private static final String ERROR_AGENT_CONTEXT_MISSING = "agentContext not exists";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "reason": {"type": "string", "description": "本次请求静态校验的原因"}
              }
            }
            """;

    @Resource
    private AuthoringDraftChangeService authoringDraftChangeService;

    @Resource
    private AiCodingEventPayloadCodec aiCodingEventPayloadCodec;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(AuthoringDraftChangeService.TOOL_VALIDATE_CAPABILITY_DRAFT)
                .description("Validate the current Capability Center draft without saving it. "
                        + "This is structural validation only and is not a live API dry-run.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /**
     * 执行当前能力草稿的只读静态校验。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        BaseAgentContext agentContext = requireAgentContext(toolContext);
        Map<String, String> context = buildContext(agentContext);
        try {
            log.info("能力草稿静态校验Tool开始执行, draftId={}, revision={}, sessionId={}",
                    context.get(FIELD_DRAFT_ID), context.get(FIELD_REVISION), context.get(FIELD_SESSION_ID));
            return aiCodingEventPayloadCodec.toJson(authoringDraftChangeService.validateCapabilityDraft(context));
        } catch (IllegalArgumentException e) {
            log.warn("能力草稿静态校验Tool参数校验失败, draftId={}, revision={}, traceId={}, error={}",
                    context.get(FIELD_DRAFT_ID), context.get(FIELD_REVISION), context.get(FIELD_TRACE_ID),
                    e.getMessage());
            throw new ToolException(e.getMessage(), e, ToolException.ErrorCode.INVALID_PARAMS);
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
        for (String field : CONTEXT_FIELDS) {
            String value = MapUtils.getString(extraBizParam, field);
            if (StringUtils.isNotBlank(value)) {
                context.put(field, value);
            }
        }
        Object currentDraft = extraBizParam.get(FIELD_CURRENT_DRAFT);
        if (currentDraft != null) {
            context.put(FIELD_CURRENT_DRAFT, currentDraft instanceof String
                                            ? String.valueOf(currentDraft) : JsonSupport.toJSON(currentDraft));
        }
        return context;
    }
}
