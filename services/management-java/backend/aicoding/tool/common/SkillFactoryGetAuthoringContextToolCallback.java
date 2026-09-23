package dev.a2flow.management.aicoding.tool.common;

import jakarta.annotation.Resource;

import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.aicoding.dependency.SkillAuthoringDependencyService;
import dev.a2flow.management.aicoding.tool.skill.SkillFactoryDependencyToolSupport;

import lombok.extern.slf4j.Slf4j;

/**
 * 当前 Skill 作者上下文查询 Tool。
 *
 * <p>模型无需也不能传 workspaceId；该 Tool 从后端可信上下文读取工作区，并返回工作台已经保存的
 * 能力、组件稳定引用。发布源由后续环境感知查询选择；该 Tool 不创建绑定、不写 SKILL.md，也不返回
 * 运行权限。
 */
@Slf4j
@Component
public class SkillFactoryGetAuthoringContextToolCallback implements ToolCallback {

    private static final String INPUT_SCHEMA = "{\"type\":\"object\",\"properties\":{},"
            + "\"additionalProperties\":false}";

    @Resource
    private SkillAuthoringDependencyService dependencyService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(SkillAuthoringDependencyService.TOOL_GET_AUTHORING_CONTEXT)
                .description("Read the current Skill's trusted stable capability and component references. "
                        + "Do not provide workspace identity in tool input.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return SkillFactoryDependencyToolSupport.rejectUntrustedCall();
    }

    /** 读取当前 Skill 已保存的作者引用上下文。 */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        SkillFactoryDependencyToolSupport.parseObject(toolInput, java.util.Collections.emptyList());
        String workspaceId = SkillFactoryDependencyToolSupport.trustedWorkspaceId(toolContext);
        log.info("Skill作者上下文Tool开始执行, workspaceId={}", workspaceId);
        return JsonSupport.toJSON(dependencyService.getAuthoringContext(workspaceId));
    }
}
