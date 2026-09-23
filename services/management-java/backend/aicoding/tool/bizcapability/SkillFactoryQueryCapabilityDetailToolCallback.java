package dev.a2flow.management.aicoding.tool.bizcapability;

import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.aicoding.dependency.SkillAuthoringDependencyService;
import dev.a2flow.management.aicoding.tool.skill.SkillFactoryDependencyToolSupport;

import lombok.extern.slf4j.Slf4j;

/**
 * 当前 Skill 正式业务能力版本详情查询 Tool。
 *
 * <p>模型只提供 actionCode 和正式 version；服务端还会校验该版本已被当前 Skill 选择，避免把该
 * Tool 当成任意能力目录查询入口。能力执行继续由既有动态业务能力 Tool 负责。
 */
@Slf4j
@Component
public class SkillFactoryQueryCapabilityDetailToolCallback implements ToolCallback {

    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_VERSION = "version";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "actionCode": {"type": "string", "description": "Published capability actionCode"},
                "version": {"type": "integer", "minimum": 1, "description": "Published version"}
              },
              "required": ["actionCode", "version"],
              "additionalProperties": false
            }
            """;

    @Resource
    private SkillAuthoringDependencyService dependencyService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(SkillAuthoringDependencyService.TOOL_QUERY_CAPABILITY_DETAIL)
                .description("Read exact details for a published capability version already referenced by "
                        + "the current Skill. This tool does not execute the capability.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return SkillFactoryDependencyToolSupport.rejectUntrustedCall();
    }

    /** 查询当前 Skill 已选择的正式能力版本详情。 */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        Map<String, Object> input = SkillFactoryDependencyToolSupport.parseObject(toolInput,
                List.of(FIELD_ACTION_CODE, FIELD_VERSION));
        String workspaceId = SkillFactoryDependencyToolSupport.trustedWorkspaceId(toolContext);
        String actionCode = MapUtils.getString(input, FIELD_ACTION_CODE);
        int version = MapUtils.getIntValue(input, FIELD_VERSION);
        log.info("Skill能力版本详情Tool开始执行, workspaceId={}, actionCode={}, version={}",
                workspaceId, actionCode, version);
        return JsonSupport.toJSON(
                dependencyService.queryCapabilityDetail(workspaceId, actionCode, version));
    }
}
