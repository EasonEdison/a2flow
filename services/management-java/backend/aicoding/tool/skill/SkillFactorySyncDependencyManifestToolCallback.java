package dev.a2flow.management.aicoding.tool.skill;

import java.util.Collections;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import com.google.common.collect.Maps;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.aicoding
        .SkillFactoryManagedSkillDocumentService;
import dev.a2flow.management.aicoding.dependency.SkillAuthoringDependencyService;
import dev.a2flow.management.aicoding.dependency
        .SkillAuthoringDependencyService.ManagedDependencyCompilation;

import lombok.extern.slf4j.Slf4j;

/**
 * SKILL.md CARD组件、A2UI Application 与业务能力说明编译 Tool。
 *
 * <p>模型根据用户自然语言中的依赖编译意图调用本 Tool。Tool 只根据 workspace DB 中的权威绑定和
 * PRT 环境解析器只生成当前非空依赖类别的完整 marker 区块并返回给模型，不创建 Patch，也不写
 * SKILL.md。模型收到结果后必须再调用普通 {@code propose_patch} 原子新增或替换这些区块，让用户在
 * 标准 Patch 卡片中审阅后落盘。历史 {@code skillfactory-dependencies} 区块在本次 Patch 中删除，不再
 * 生成。区块不固化易变化的 Schema；模型不能提供资产身份、workspaceId 或正文。
 */
@Slf4j
@Component
public class SkillFactorySyncDependencyManifestToolCallback implements ToolCallback {

    private static final String INPUT_SCHEMA = "{\"type\":\"object\",\"properties\":{},"
            + "\"additionalProperties\":false}";
    private static final String TARGET_FILE = "SKILL.md";
    private static final String FIELD_TARGET_FILE = "targetFile";
    private static final String FIELD_MANAGED_BLOCKS = "managedBlocks";
    private static final String FIELD_COMPONENT_GUIDANCE = "componentGuidance";
    private static final String FIELD_CAPABILITY_GUIDANCE = "capabilityGuidance";
    private static final String FIELD_A2UI_APPLICATION_GUIDANCE = "a2uiApplicationGuidance";
    private static final String FIELD_COMPONENTS = "components";
    private static final String FIELD_A2UI_APPLICATIONS = "a2uiApplications";
    private static final String FIELD_ACTION_CODES = "actionCodes";
    private static final String FIELD_INSTRUCTION = "instruction";
    private static final String PATCH_INSTRUCTION =
            "读取当前 SKILL.md：对 managedBlocks 中实际返回的 marker 区块，缺失则追加，存在则从起止 "
                    + "marker 整体替换；三类受管区块中未出现在 managedBlocks 的类别，连同对应说明标题"
                    + "整体删除；如果存在旧 skillfactory-dependencies 区块，连同运行依赖标题一起删除。"
                    + "随后通过一次 propose_patch 原子生成可审阅 Patch。不要改写区块正文、重复追加或"
                    + "声称 Tool 已直接修改文件。";

    @Resource
    private SkillAuthoringDependencyService dependencyService;

    @Resource
    private SkillFactoryManagedSkillDocumentService managedSkillDocumentService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(SkillAuthoringDependencyService.TOOL_SYNC_DEPENDENCY_MANIFEST)
                .description("When the user asks to add, update, compile, or synchronize the current Skill's "
                        + "bound dependencies, CARD component guidance, A2UI Application guidance, or business "
                        + "capability guidance, return only non-empty current managed guidance blocks generated "
                        + "from trusted bindings. After receiving the result, read SKILL.md, remove omitted stale "
                        + "managed sections and any legacy skillfactory-dependencies block, and call propose_patch "
                        + "once to append or replace the returned blocks for human review. This tool "
                        + "takes no arguments and never creates a patch or edits files. "
                        + "Do not call it for unrelated file changes.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return SkillFactoryDependencyToolSupport.rejectUntrustedCall();
    }

    /** 根据权威绑定仅返回非空类别的完整marker区块，由模型继续调用一次propose_patch。 */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        SkillFactoryDependencyToolSupport.parseObject(toolInput, Collections.emptyList());
        String workspaceId = SkillFactoryDependencyToolSupport.trustedWorkspaceId(toolContext);
        ManagedDependencyCompilation compilation =
                dependencyService.buildManagedDependencyCompilation(workspaceId);
        Map<String, String> managedBlocks = Maps.newLinkedHashMap();
        String componentGuidance = managedSkillDocumentService
                .buildComponentGuidanceBlock(compilation.getComponentGuidance());
        if (StringUtils.isNotBlank(componentGuidance)) {
            managedBlocks.put(FIELD_COMPONENT_GUIDANCE, componentGuidance);
        }
        String a2uiApplicationGuidance = managedSkillDocumentService
                .buildA2uiApplicationGuidanceBlock(compilation.getA2uiApplicationGuidance());
        if (StringUtils.isNotBlank(a2uiApplicationGuidance)) {
            managedBlocks.put(FIELD_A2UI_APPLICATION_GUIDANCE, a2uiApplicationGuidance);
        }
        String capabilityGuidance = managedSkillDocumentService
                .buildCapabilityGuidanceBlock(compilation.getCapabilityGuidance());
        if (StringUtils.isNotBlank(capabilityGuidance)) {
            managedBlocks.put(FIELD_CAPABILITY_GUIDANCE, capabilityGuidance);
        }
        Map<String, Object> result = Maps.newLinkedHashMap();
        result.put(FIELD_TARGET_FILE, TARGET_FILE);
        result.put(FIELD_MANAGED_BLOCKS, managedBlocks);
        result.put(FIELD_COMPONENTS, compilation.getComponentCodes());
        result.put(FIELD_A2UI_APPLICATIONS, compilation.getA2uiApplicationCodes());
        result.put(FIELD_ACTION_CODES, compilation.getActionCodes());
        result.put(FIELD_INSTRUCTION, PATCH_INSTRUCTION);
        log.info("Skill依赖编译Tool已返回非空受管区块, workspaceId={}, componentCount={}, "
                        + "a2uiApplicationCount={}, capabilityCount={}, componentLength={}, "
                        + "a2uiApplicationLength={}, capabilityLength={}",
                workspaceId, compilation.getComponentCodes().size(),
                compilation.getA2uiApplicationCodes().size(), compilation.getActionCodes().size(),
                StringUtils.length(managedBlocks.get(FIELD_COMPONENT_GUIDANCE)),
                StringUtils.length(managedBlocks.get(FIELD_A2UI_APPLICATION_GUIDANCE)),
                StringUtils.length(managedBlocks.get(FIELD_CAPABILITY_GUIDANCE)));
        return JsonSupport.toJSON(result);
    }
}
