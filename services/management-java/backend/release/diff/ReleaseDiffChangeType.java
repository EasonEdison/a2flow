package dev.a2flow.management.release.diff;

/**
 * 发布 Diff 中文件条目的变化类型。
 *
 * <p>该枚举只描述两个不可变资源集合之间的文件身份变化，不负责判断资产是否允许发布。
 */
public enum ReleaseDiffChangeType {
    ADDED,
    MODIFIED,
    DELETED,
    RENAMED
}
