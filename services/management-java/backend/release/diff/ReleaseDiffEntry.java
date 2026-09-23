package dev.a2flow.management.release.diff;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 发布 Diff 的单个文件条目。
 *
 * <p>列表请求主要返回路径、类型、摘要和统计；详情请求为选中的文本/JSON 文件补充 hunks。
 * 超过共享限制时必须通过 truncated 和 truncatedReason 明确说明，禁止静默截断。
 */
@Data
@Accessors(chain = true)
public class ReleaseDiffEntry {

    private String path;
    private String oldPath;
    private ReleaseDiffChangeType changeType;
    private ReleaseDiffContentType contentType;
    private String language;
    private String beforeDigest;
    private String afterDigest;
    private Long beforeSize;
    private Long afterSize;
    private Integer additions;
    private Integer deletions;
    private Boolean truncated = false;
    private String truncatedReason;
    private String resourceType;
    private Map<String, Object> details = new LinkedHashMap<>();
    private List<ReleaseDiffHunk> hunks = new ArrayList<>();
}
