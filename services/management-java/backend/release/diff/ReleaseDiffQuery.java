package dev.a2flow.management.release.diff;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 一次发布 Diff 查询的展示参数。
 *
 * <p>列表查询不传 entryPath，只返回文件条目摘要；详情查询传 entryPath，仅为该文件生成 hunks。
 * contextLines 控制每个变更块前后的上下文行数，避免前端获取无边界的完整文件内容。
 */
@Data
@Accessors(chain = true)
public class ReleaseDiffQuery {

    private String entryPath;
    private ReleaseDiffViewMode viewMode = ReleaseDiffViewMode.UNIFIED;
    private Integer contextLines;
}
