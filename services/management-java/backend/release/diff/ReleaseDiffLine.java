package dev.a2flow.management.release.diff;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * GitHub 风格发布 Diff 的单行数据。
 *
 * <p>删除行只有 oldLineNumber，新增行只有 newLineNumber，上下文行同时具有两个行号。
 */
@Data
@Accessors(chain = true)
public class ReleaseDiffLine {

    private ReleaseDiffLineType type;
    private Integer oldLineNumber;
    private Integer newLineNumber;
    private String content;
}
