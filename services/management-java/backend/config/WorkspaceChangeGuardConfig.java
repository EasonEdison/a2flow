package dev.a2flow.management.config;

import lombok.Data;

/**
 * SkillFactory workspace 文件变更检测配置。
 *
 * <p>该配置挂在对应 bizKey 的 `SkillFactoryAgentBizSummaryConfig.propertiesConfig` 下，用于控制
 * workspace 变更摘要的展示边界和 Patch 文件级三方合并策略。模型调用前的实时快照与变更事实注入、
 * Patch 确认时的安全合并检测都是新鲜度不变量，不允许通过配置关闭。本类只描述展示参数和当前策略，
 * 不读取文件、不写 observation，也不绑定具体 engine。
 */
@Data
@SuppressWarnings("checkstyle:MagicNumber")
public class WorkspaceChangeGuardConfig {

    public static final String PATCH_CONFLICT_STRATEGY_THREE_WAY_MERGE_TOUCHED_FILES =
            "THREE_WAY_MERGE_TOUCHED_FILES";

    /**
     * 是否在 observation 里附带小段变更文件预览，帮助模型知道需要重新读取哪些文件。
     */
    private boolean includeChangedFilePreview = true;

    /**
     * 单次 observation 最多展示多少个变更文件。
     */
    private int maxChangedFilesInSummary = 10;

    /**
     * 每个文件预览最多读取的字符数。
     */
    private int maxFilePreviewChars = 1200;

    /**
     * Patch 确认时的冲突策略标识；当前固定为选中文件三方合并，不提供跳过冲突检查的策略。
     */
    private String patchConflictStrategy = PATCH_CONFLICT_STRATEGY_THREE_WAY_MERGE_TOUCHED_FILES;

    public int safeMaxChangedFilesInSummary() {
        return maxChangedFilesInSummary <= 0 ? 10 : Math.min(maxChangedFilesInSummary, 50);
    }

    public int safeMaxFilePreviewChars() {
        return maxFilePreviewChars <= 0 ? 1200 : Math.min(maxFilePreviewChars, 10000);
    }
}
