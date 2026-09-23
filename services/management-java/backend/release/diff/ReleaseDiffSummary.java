package dev.a2flow.management.release.diff;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 一次发布 Diff 的聚合统计。
 *
 * <p>统计覆盖当前响应内全部变化文件；即使列表请求没有返回 hunks，也会返回增加/删除行数。
 * 如果超大文件被截断，truncatedReason 会明确指出统计与 hunk 均为受限结果。
 */
@Data
@Accessors(chain = true)
public class ReleaseDiffSummary {

    private Integer changedFiles;
    private Integer additions;
    private Integer deletions;
    private Boolean truncated = false;
    private String truncatedReason;
}
