package dev.a2flow.management.release.diff;

import java.util.ArrayList;
import java.util.List;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * RELEASE_DIFF 对外返回的统一强类型文档。
 *
 * <p>from/to 描述比较两端的业务版本标签，summary 和 entries 提供统一的跨领域 Diff 契约。
 * 该模型不携带领域原始响应 Map，Skill、组件和能力必须全部转换为本结构。
 */
@Data
@Accessors(chain = true)
public class ReleaseDiffDocument {

    private String assetType;
    private String assetKey;
    private String currentDigest;
    private Integer targetVersion;
    private Boolean hasTarget;
    private String from;
    private String to;
    private String requestedEntryPath;
    private ReleaseDiffViewMode viewMode;
    private ReleaseDiffSummary summary = new ReleaseDiffSummary();
    private List<ReleaseDiffEntry> entries = new ArrayList<>();
}
