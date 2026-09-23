package dev.a2flow.management.release.diff;

/**
 * 发布 Diff 前端展示模式。
 *
 * <p>共享后端的行级契约对统一和并排模式保持一致，前端可以按该模式重新排版相同的 Diff 行。
 */
public enum ReleaseDiffViewMode {
    UNIFIED,
    SPLIT
}
