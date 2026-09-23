package dev.a2flow.management.release.diff;

/**
 * 发布 Diff 单行的展示语义。
 *
 * <p>前端据此渲染上下文、增加和删除行；行号由共享 Diff 引擎统一计算。
 */
public enum ReleaseDiffLineType {
    CONTEXT,
    ADD,
    DELETE
}
