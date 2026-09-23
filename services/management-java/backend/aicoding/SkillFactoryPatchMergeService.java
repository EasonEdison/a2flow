package dev.a2flow.management.aicoding;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.aicoding.domain
        .SkillFactoryPatchMergePlan;
import dev.a2flow.management.aicoding.domain
        .SkillFactoryPreparedPatchChange;
import dev.a2flow.management.fileguard.WorkspaceTextMergeResult;
import dev.a2flow.management.fileguard.WorkspaceThreeWayMergeService;

/**
 * AI Coding Patch 文件级三方合并规则服务。
 *
 * <p>该服务按 ADD、MODIFY、DELETE 语义生成整批待执行计划。它只计算结果，不读取或写入文件，
 * 不更新 Patch 状态，也不处理审批。
 */
@Service
public class SkillFactoryPatchMergeService {

    private static final String FIELD_PATH = "path";
    private static final String FIELD_CHANGE_TYPE = "changeType";
    private static final String FIELD_CONTENT = "content";
    private static final String CHANGE_TYPE_ADD = "ADD";
    private static final String CHANGE_TYPE_MODIFY = "MODIFY";
    private static final String CHANGE_TYPE_DELETE = "DELETE";

    @Resource
    private WorkspaceThreeWayMergeService workspaceThreeWayMergeService;

    /**
     * 为全部选中文件生成合并计划；任一文件冲突时，调用方不得执行计划中的写入动作。
     */
    public SkillFactoryPatchMergePlan prepare(List<Map<String, Object>> selectedChanges,
            Map<String, String> baseContentMap, Map<String, String> currentContentMap,
            boolean useCurrentContentAsLegacyBase, Function<String, Path> pathResolver) throws IOException {
        SkillFactoryPatchMergePlan plan = new SkillFactoryPatchMergePlan();
        for (Map<String, Object> change : selectedChanges) {
            String relativePath = StringUtils.trimToEmpty(MapUtils.getString(change, FIELD_PATH));
            if (StringUtils.isBlank(relativePath)) {
                throw new IllegalArgumentException("path is required");
            }
            if (!baseContentMap.containsKey(relativePath) && !useCurrentContentAsLegacyBase) {
                plan.addConflict(relativePath);
                continue;
            }
            String baseContent = baseContentMap.containsKey(relativePath)
                    ? baseContentMap.get(relativePath) : currentContentMap.get(relativePath);
            SkillFactoryPreparedPatchChange preparedChange = prepareChange(relativePath,
                    pathResolver.apply(relativePath),
                    StringUtils.upperCase(MapUtils.getString(change, FIELD_CHANGE_TYPE)),
                    baseContent, currentContentMap.get(relativePath),
                    StringUtils.defaultString(MapUtils.getString(change, FIELD_CONTENT)));
            if (preparedChange == null) {
                plan.addConflict(relativePath);
            } else {
                plan.addChange(preparedChange);
            }
        }
        return plan;
    }

    private SkillFactoryPreparedPatchChange prepareChange(String relativePath, Path targetPath, String changeType,
            String baseContent, String currentContent, String proposedContent) throws IOException {
        if (CHANGE_TYPE_ADD.equals(changeType)) {
            if (currentContent == null) {
                return SkillFactoryPreparedPatchChange.write(relativePath, targetPath, proposedContent);
            }
            return StringUtils.equals(currentContent, proposedContent)
                    ? SkillFactoryPreparedPatchChange.none(relativePath, targetPath) : null;
        }
        if (CHANGE_TYPE_DELETE.equals(changeType)) {
            if (currentContent == null) {
                return SkillFactoryPreparedPatchChange.none(relativePath, targetPath);
            }
            return baseContent != null && StringUtils.equals(baseContent, currentContent)
                    ? SkillFactoryPreparedPatchChange.delete(relativePath, targetPath) : null;
        }
        if (!CHANGE_TYPE_MODIFY.equals(changeType) || baseContent == null || currentContent == null) {
            return null;
        }
        if (StringUtils.equals(currentContent, proposedContent)) {
            return SkillFactoryPreparedPatchChange.none(relativePath, targetPath);
        }
        if (StringUtils.equals(baseContent, currentContent)) {
            return SkillFactoryPreparedPatchChange.write(relativePath, targetPath, proposedContent);
        }
        WorkspaceTextMergeResult mergeResult =
                workspaceThreeWayMergeService.merge(baseContent, currentContent, proposedContent);
        if (mergeResult.isConflict()) {
            return null;
        }
        return StringUtils.equals(currentContent, mergeResult.getMergedContent())
                ? SkillFactoryPreparedPatchChange.none(relativePath, targetPath)
                : SkillFactoryPreparedPatchChange.write(
                        relativePath, targetPath, mergeResult.getMergedContent());
    }
}
