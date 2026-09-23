package dev.a2flow.management.aicoding.tool.bizcapability;

import java.util.Collections;
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
import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionToolProvider;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;
import dev.a2flow.management.lifecycle.CapabilityActionDraftService;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.release.ReleaseEnvironment;

import lombok.extern.slf4j.Slf4j;

/**
 * 能力中心作者工作台的只读真实调用 Tool。
 *
 * <p>该 Tool 从可信 `ToolContext` 获取当前已保存 draftId、revision 和 B 端 Cookie，模型只提供
 * `sampleArguments`。它使用与正式动态业务 Tool 相同的 Provider/Executor，但本期只允许 READ，
 * 不接受模型指定 URL、Path、Header、Cookie、环境或草稿身份。
 */
@Component
@Slf4j
public class SkillFactoryCapabilityDryRunToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "capability_dry_run";

    private static final String FIELD_AGENT_CONTEXT = "agentContext";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_REVISION = "revision";
    private static final String FIELD_SAMPLE_ARGUMENTS = "sampleArguments";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "sampleArguments": {
                  "type": "object",
                  "description": "当前已保存能力草稿的模型可见示例参数"
                }
              },
              "required": ["sampleArguments"],
              "additionalProperties": false
            }
            """;

    @Resource
    private CapabilityActionDraftService capabilityActionDraftService;

    @Resource
    private CapabilityActionToolProvider capabilityActionToolProvider;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_NAME)
                .description("Run the current saved READ-only CapabilityAction draft through its approved "
                        + "controlled HTTP binding. Only provide sampleArguments; destination, headers, Cookie, "
                        + "environment, draftId and revision come from trusted runtime context.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /**
     * 使用当前登录态执行已保存草稿的只读受控 HTTP 验证。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        BaseAgentContext agentContext = requireAgentContext(toolContext);
        Map<String, Object> extraBizParam = agentContext.getExtraBizParam() == null
                                            ? Collections.emptyMap() : agentContext.getExtraBizParam();
        String draftId = MapUtils.getString(extraBizParam, FIELD_DRAFT_ID);
        int trustedRevision = MapUtils.getIntValue(extraBizParam, FIELD_REVISION, 0);
        if (StringUtils.isBlank(draftId) || trustedRevision <= 0) {
            throw new ToolException("trusted draftId and revision are required",
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        Map<String, Object> input = parseInput(toolInput);
        Object sampleArguments = input.get(FIELD_SAMPLE_ARGUMENTS);
        if (!(sampleArguments instanceof Map)) {
            throw new ToolException("sampleArguments must be a JSON object",
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        CapabilityActionDraft draft = capabilityActionDraftService.detail(draftId);
        if (!Objects.equals(draft.getRevision(), trustedRevision)) {
            throw new ToolException("capability draft revision changed; save and retry dry-run",
                    ToolException.ErrorCode.VALIDATION_ERROR);
        }
        log.info("能力中心dry-run开始执行, draftId={}, revision={}, actionCode={}, clientType={}",
                draftId, trustedRevision, nestedActionCode(draft), agentContext.getClient());
        ToolCallback actionTool = capabilityActionToolProvider.create(
                draft, ReleaseEnvironment.PRT, agentContext.getClient());
        return actionTool.call(JsonSupport.toJSON(sampleArguments), toolContext);
    }

    private BaseAgentContext requireAgentContext(ToolContext toolContext) {
        if (toolContext == null || toolContext.getContext() == null) {
            throw new ToolException("toolContext not exists", ToolException.ErrorCode.PERMISSION_DENIED);
        }
        BaseAgentContext agentContext = (BaseAgentContext) toolContext.getContext().get(FIELD_AGENT_CONTEXT);
        if (agentContext == null) {
            throw new ToolException("agentContext not exists", ToolException.ErrorCode.PERMISSION_DENIED);
        }
        return agentContext;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseInput(String toolInput) {
        try {
            Object parsed = JsonSupport.fromJSON(toolInput, Object.class);
            if (!(parsed instanceof Map)) {
                throw new IllegalArgumentException("tool input must be a JSON object");
            }
            Map<String, Object> input = (Map<String, Object>) parsed;
            if (input.size() != 1 || !input.containsKey(FIELD_SAMPLE_ARGUMENTS)) {
                throw new IllegalArgumentException("only sampleArguments is allowed");
            }
            return input;
        } catch (Exception e) {
            throw new ToolException("capability dry-run input is invalid", e,
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
    }

    @SuppressWarnings("unchecked")
    private String nestedActionCode(CapabilityActionDraft draft) {
        Object basicInfoValue = draft.getDraft().get("basicInfo");
        if (!(basicInfoValue instanceof Map)) {
            return StringUtils.EMPTY;
        }
        return MapUtils.getString((Map<String, Object>) basicInfoValue, "actionCode", StringUtils.EMPTY);
    }
}
