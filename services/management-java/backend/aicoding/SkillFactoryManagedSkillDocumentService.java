package dev.a2flow.management.aicoding;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

/**
 * SKILL.md 受管区块合并与防篡改服务。
 *
 * <p>上游由依赖编译和通用 Patch 校验调用；本类只处理固定配对 marker，不读取绑定、数据库或工作区，
 * 也不决定文件是否可写。依赖同步 Tool 返回当前非空类别的 CARD组件、A2UI Application 和业务能力
 * 完整区块后，模型可以通过一次普通 {@code propose_patch} 新增、替换或删除已失效区块；任一保留区块的
 * marker 缺失、重复或逆序时一律失败。
 * 已废弃的 {@code skillfactory-dependencies} 只能保持原样或连同标题删除，不能新增或修改。所有受管
 * 内容变化都由调用方强制进入人工审阅。
 */
@Component
public class SkillFactoryManagedSkillDocumentService {

    private static final String DEPENDENCY_SECTION_HEADING = "## 运行依赖";
    private static final String DEPENDENCY_MANAGED_START = "<!-- skillfactory-dependencies:start -->";
    private static final String DEPENDENCY_MANAGED_END = "<!-- skillfactory-dependencies:end -->";
    private static final String COMPONENT_GUIDANCE_SECTION_HEADING = "## 组件使用说明";
    private static final String COMPONENT_GUIDANCE_MANAGED_START =
            "<!-- skillfactory-component-guidance:start -->";
    private static final String COMPONENT_GUIDANCE_MANAGED_END =
            "<!-- skillfactory-component-guidance:end -->";
    private static final String CAPABILITY_GUIDANCE_SECTION_HEADING = "## 业务能力使用说明";
    private static final String A2UI_APPLICATION_GUIDANCE_SECTION_HEADING =
            "## A2UI Application 使用说明";
    private static final String CAPABILITY_GUIDANCE_MANAGED_START =
            "<!-- skillfactory-capability-guidance:start -->";
    private static final String CAPABILITY_GUIDANCE_MANAGED_END =
            "<!-- skillfactory-capability-guidance:end -->";
    private static final String A2UI_APPLICATION_GUIDANCE_MANAGED_START =
            "<!-- skillfactory-a2ui-application-guidance:start -->";
    private static final String A2UI_APPLICATION_GUIDANCE_MANAGED_END =
            "<!-- skillfactory-a2ui-application-guidance:end -->";
    private static final String ERROR_MANAGED_DEPENDENCY_MARKER =
            "SKILL.md managed dependency markers are incomplete";
    private static final String ERROR_MANAGED_DEPENDENCY_ADDITION =
            "SKILL.md legacy managed dependency block cannot be added";
    private static final String ERROR_MANAGED_DEPENDENCY_MODIFICATION =
            "SKILL.md legacy managed dependency block can only be removed";
    private static final String ERROR_MANAGED_COMPONENT_GUIDANCE_MARKER =
            "SKILL.md managed component guidance markers are incomplete";
    private static final String ERROR_MANAGED_COMPONENT_GUIDANCE_BODY_MARKER =
            "component guidance body must not contain managed markers";
    private static final String ERROR_MANAGED_CAPABILITY_GUIDANCE_MARKER =
            "SKILL.md managed capability guidance markers are incomplete";
    private static final String ERROR_MANAGED_CAPABILITY_GUIDANCE_BODY_MARKER =
            "capability guidance body must not contain managed markers";
    private static final String ERROR_MANAGED_A2UI_APPLICATION_GUIDANCE_MARKER =
            "SKILL.md managed A2UI Application guidance markers are incomplete";
    private static final String ERROR_MANAGED_A2UI_APPLICATION_GUIDANCE_BODY_MARKER =
            "A2UI Application guidance body must not contain managed markers";

    /** 将可信组件说明正文包装成模型可直接交给 propose_patch 的完整配对 marker 区块。 */
    public String buildComponentGuidanceBlock(String componentGuidance) {
        return buildManagedBlock(componentGuidance, COMPONENT_GUIDANCE_MANAGED_START,
                COMPONENT_GUIDANCE_MANAGED_END, ERROR_MANAGED_COMPONENT_GUIDANCE_BODY_MARKER);
    }

    /** 将可信业务能力说明正文包装成模型可直接交给 propose_patch 的完整配对 marker 区块。 */
    public String buildCapabilityGuidanceBlock(String capabilityGuidance) {
        return buildManagedBlock(capabilityGuidance, CAPABILITY_GUIDANCE_MANAGED_START,
                CAPABILITY_GUIDANCE_MANAGED_END, ERROR_MANAGED_CAPABILITY_GUIDANCE_BODY_MARKER);
    }

    /** 将可信A2UI Application说明正文包装成模型可直接交给propose_patch的完整配对marker区块。 */
    public String buildA2uiApplicationGuidanceBlock(String applicationGuidance) {
        return buildManagedBlock(applicationGuidance,
                A2UI_APPLICATION_GUIDANCE_MANAGED_START,
                A2UI_APPLICATION_GUIDANCE_MANAGED_END,
                ERROR_MANAGED_A2UI_APPLICATION_GUIDANCE_BODY_MARKER);
    }

    /**
     * 校验普通 Patch 的受管区块边界，并返回任一受管内容是否发生变化。
     *
     * <p>模型可以把依赖同步 Tool 返回的三类活动区块一次性新增或替换，也可以删除 Tool 已不再返回的
     * 失效区块。已废弃依赖区块只允许保持原样或删除。返回 true 时调用方必须强制进入人工 Patch 审阅，
     * 不能按自动审批模式直接写入。
     */
    public boolean validatePatchAndDetectManagedGuidanceChange(String oldContent, String newContent) {
        String oldDependencyBlock = extractManagedBlock(oldContent,
                DEPENDENCY_MANAGED_START, DEPENDENCY_MANAGED_END, ERROR_MANAGED_DEPENDENCY_MARKER);
        String newDependencyBlock = extractManagedBlock(newContent,
                DEPENDENCY_MANAGED_START, DEPENDENCY_MANAGED_END, ERROR_MANAGED_DEPENDENCY_MARKER);
        String oldComponentBlock = extractManagedBlock(oldContent, COMPONENT_GUIDANCE_MANAGED_START,
                COMPONENT_GUIDANCE_MANAGED_END, ERROR_MANAGED_COMPONENT_GUIDANCE_MARKER);
        String newComponentBlock = extractManagedBlock(newContent, COMPONENT_GUIDANCE_MANAGED_START,
                COMPONENT_GUIDANCE_MANAGED_END, ERROR_MANAGED_COMPONENT_GUIDANCE_MARKER);
        String oldCapabilityBlock = extractManagedBlock(oldContent, CAPABILITY_GUIDANCE_MANAGED_START,
                CAPABILITY_GUIDANCE_MANAGED_END, ERROR_MANAGED_CAPABILITY_GUIDANCE_MARKER);
        String newCapabilityBlock = extractManagedBlock(newContent, CAPABILITY_GUIDANCE_MANAGED_START,
                CAPABILITY_GUIDANCE_MANAGED_END, ERROR_MANAGED_CAPABILITY_GUIDANCE_MARKER);
        String oldA2uiApplicationBlock = extractManagedBlock(oldContent,
                A2UI_APPLICATION_GUIDANCE_MANAGED_START,
                A2UI_APPLICATION_GUIDANCE_MANAGED_END,
                ERROR_MANAGED_A2UI_APPLICATION_GUIDANCE_MARKER);
        String newA2uiApplicationBlock = extractManagedBlock(newContent,
                A2UI_APPLICATION_GUIDANCE_MANAGED_START,
                A2UI_APPLICATION_GUIDANCE_MANAGED_END,
                ERROR_MANAGED_A2UI_APPLICATION_GUIDANCE_MARKER);
        validateManagedHeading(newContent, DEPENDENCY_SECTION_HEADING, newDependencyBlock,
                ERROR_MANAGED_DEPENDENCY_MARKER);
        validateManagedHeading(newContent, COMPONENT_GUIDANCE_SECTION_HEADING, newComponentBlock,
                ERROR_MANAGED_COMPONENT_GUIDANCE_MARKER);
        validateManagedHeading(newContent, CAPABILITY_GUIDANCE_SECTION_HEADING, newCapabilityBlock,
                ERROR_MANAGED_CAPABILITY_GUIDANCE_MARKER);
        validateManagedHeading(newContent, A2UI_APPLICATION_GUIDANCE_SECTION_HEADING,
                newA2uiApplicationBlock, ERROR_MANAGED_A2UI_APPLICATION_GUIDANCE_MARKER);
        validateLegacyDependencyBlockChange(oldDependencyBlock, newDependencyBlock);
        return !StringUtils.equals(oldDependencyBlock, newDependencyBlock)
                || !StringUtils.equals(oldComponentBlock, newComponentBlock)
                || !StringUtils.equals(oldCapabilityBlock, newCapabilityBlock)
                || !StringUtils.equals(oldA2uiApplicationBlock, newA2uiApplicationBlock)
                || headingCountChanged(oldContent, newContent, DEPENDENCY_SECTION_HEADING)
                || headingCountChanged(oldContent, newContent, COMPONENT_GUIDANCE_SECTION_HEADING)
                || headingCountChanged(oldContent, newContent, CAPABILITY_GUIDANCE_SECTION_HEADING)
                || headingCountChanged(oldContent, newContent,
                        A2UI_APPLICATION_GUIDANCE_SECTION_HEADING);
    }

    private String buildManagedBlock(String content, String startMarker, String endMarker,
            String bodyMarkerError) {
        String body = StringUtils.stripEnd(StringUtils.defaultString(content), null);
        if (StringUtils.isBlank(body)) {
            return StringUtils.EMPTY;
        }
        if (StringUtils.contains(body, startMarker) || StringUtils.contains(body, endMarker)) {
            throw new IllegalArgumentException(bodyMarkerError);
        }
        return startMarker + "\n" + body + "\n" + endMarker;
    }

    private void validateLegacyDependencyBlockChange(String oldBlock, String newBlock) {
        if (StringUtils.isEmpty(oldBlock) && StringUtils.isNotEmpty(newBlock)) {
            throw new IllegalArgumentException(ERROR_MANAGED_DEPENDENCY_ADDITION);
        }
        if (StringUtils.isNotEmpty(oldBlock) && StringUtils.isNotEmpty(newBlock)
                && !StringUtils.equals(oldBlock, newBlock)) {
            throw new IllegalArgumentException(ERROR_MANAGED_DEPENDENCY_MODIFICATION);
        }
    }

    private void validateManagedHeading(String content, String sectionHeading, String managedBlock,
            String markerError) {
        int headingCount = StringUtils.countMatches(StringUtils.defaultString(content), sectionHeading);
        if (headingCount > 1 || (headingCount == 1 && StringUtils.isEmpty(managedBlock))) {
            throw new IllegalStateException(markerError);
        }
    }

    private String extractManagedBlock(String content, String startMarker, String endMarker,
            String markerError) {
        String safeContent = StringUtils.defaultString(content);
        int startCount = StringUtils.countMatches(safeContent, startMarker);
        int endCount = StringUtils.countMatches(safeContent, endMarker);
        validateManagedMarkerCounts(startCount, endCount, markerError);
        int startIndex = safeContent.indexOf(startMarker);
        int endIndex = safeContent.indexOf(endMarker);
        if (startIndex < 0 && endIndex < 0) {
            return StringUtils.EMPTY;
        }
        validateManagedMarkerIndexes(startIndex, endIndex, markerError);
        return safeContent.substring(startIndex, endIndex + endMarker.length());
    }

    private void validateManagedMarkerCounts(int startCount, int endCount, String markerError) {
        if (startCount != endCount || startCount > 1) {
            throw new IllegalStateException(markerError);
        }
    }

    private void validateManagedMarkerIndexes(int startIndex, int endIndex, String markerError) {
        if (startIndex < 0 || endIndex < startIndex) {
            throw new IllegalStateException(markerError);
        }
    }

    private boolean headingCountChanged(String oldContent, String newContent, String sectionHeading) {
        return StringUtils.countMatches(oldContent, sectionHeading)
                != StringUtils.countMatches(newContent, sectionHeading);
    }
}
