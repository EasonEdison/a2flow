package dev.a2flow.management.release.diff;

import java.util.ArrayList;
import java.util.List;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 发布 Diff 中一段连续变化及其上下文。
 *
 * <p>共享引擎根据 contextLines 合并相邻变化并生成标准 hunk 行号；前端只负责展示和折叠。
 */
@Data
@Accessors(chain = true)
public class ReleaseDiffHunk {

    private Integer oldStart;
    private Integer oldLines;
    private Integer newStart;
    private Integer newLines;
    private String header;
    private List<ReleaseDiffLine> lines = new ArrayList<>();
}
