package dev.a2flow.management.aicoding.tool.component;

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
 * 当前 Skill 正式组件版本详情查询 Tool。
 *
 * <p>模型只提供 componentCode 和正式 version；服务端校验该组件已被当前 Skill 直接选择。
 * 能力 resultContract 间接使用的组件仍属于能力版本详情，不重复写入直接组件引用。
 */
@Slf4j
@Component
public class SkillFactoryQueryComponentDetailToolCallback implements ToolCallback {

    private static final String FIELD_COMPONENT_CODE = "componentCode";
    private static final String FIELD_VERSION = "version";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "componentCode": {"type": "string", "description": "Published componentCode"},
                "version": {"type": "integer", "minimum": 1, "description": "Published version"}
              },
              "required": ["componentCode", "version"],
              "additionalProperties": false
            }
            """;

    @Resource
    private SkillAuthoringDependencyService dependencyService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(SkillAuthoringDependencyService.TOOL_QUERY_COMPONENT_DETAIL)
                .description("Read exact details for a published component version already referenced directly "
                        + "by the current Skill.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return SkillFactoryDependencyToolSupport.rejectUntrustedCall();
    }

    /** 查询当前 Skill 已选择的正式组件版本详情。 */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        Map<String, Object> input = SkillFactoryDependencyToolSupport.parseObject(toolInput,
                List.of(FIELD_COMPONENT_CODE, FIELD_VERSION));
        String workspaceId = SkillFactoryDependencyToolSupport.trustedWorkspaceId(toolContext);
        String componentCode = MapUtils.getString(input, FIELD_COMPONENT_CODE);
        int version = MapUtils.getIntValue(input, FIELD_VERSION);
        log.info("Skill组件版本详情Tool开始执行, workspaceId={}, componentCode={}, version={}",
                workspaceId, componentCode, version);
        return JsonSupport.toJSON(
                dependencyService.queryComponentDetail(workspaceId, componentCode, version));
    }
}
