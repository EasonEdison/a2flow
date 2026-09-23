package dev.a2flow.management.aicoding.tool.skill;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.aicoding.tool.common
        .SkillFactoryToolPathResolver;
import dev.a2flow.management.release
        .ReleaseModels.ReleaseReadinessInspection;

import lombok.extern.slf4j.Slf4j;

/**
 * 当前 Skill 综合准出只读巡检 Tool。
 *
 * <p>目标 workspace、skillCode 和 operator 全部来自后端 ToolContext，模型不能指定其他资产。Tool
 * 只返回确定性事实，供 mounted Skill 完成语义评审；它不执行 Skill 业务脚本、不修改文件、不写准出
 * 证据，也不触发发布。
 */
@Component
@Slf4j
public class SkillFactoryInspectReleaseReadinessToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "inspect_skill_release_readiness";

    private static final String FIELD_USER_NAME = "userName";
    private static final String TOOL_DESCRIPTION =
            "Inspect deterministic release-readiness facts for the current trusted Skill workspace. "
                    + "The tool returns the live digest, file locations, Python 3.6.8 compatibility, recent "
                    + "debug/Python runtime evidence, credential findings, authoritative current Skill metadata, "
                    + "and same-specialist peer names and descriptions. It accepts no asset identity, changes no "
                    + "file, and does not publish.";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {},
              "additionalProperties": false
            }
            """;

    @Resource
    private SkillFactoryReleaseReadinessInspectionService inspectionService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_NAME)
                .description(TOOL_DESCRIPTION)
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return SkillFactoryDependencyToolSupport.rejectUntrustedCall();
    }

    /**
     * 使用可信运行上下文巡检当前 Skill。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        SkillFactoryDependencyToolSupport.parseObject(toolInput, List.of());
        String workspaceId = SkillFactoryDependencyToolSupport.trustedWorkspaceId(toolContext);
        Map<String, String> trustedParams =
                SkillFactoryDependencyToolSupport.trustedPatchParams(toolContext);
        String operator = StringUtils.defaultString(trustedParams.get(FIELD_USER_NAME));
        Path workspacePath = SkillFactoryToolPathResolver.resolve(".", toolContext).path();
        ReleaseReadinessInspection inspection =
                inspectionService.inspect(workspaceId, workspacePath, operator);
        log.info("Skill综合准出只读巡检Tool完成, workspaceId:{}, workspaceDigest:{}, "
                        + "deterministicCheckCount:{}, operator:{}",
                workspaceId, inspection.getWorkspaceDigest(),
                inspection.getDeterministicChecks().size(), operator);
        return JsonSupport.toJSON(inspection);
    }
}
