package dev.a2flow.management.release.diff;

/**
 * 发布 Diff 资源的内容类型。
 *
 * <p>TEXT 和 JSON 允许进入行级比较；BINARY 只比较路径、大小和摘要，禁止把二进制内容放入响应。
 */
public enum ReleaseDiffContentType {
    TEXT,
    JSON,
    BINARY
}
