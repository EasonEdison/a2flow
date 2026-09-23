package dev.a2flow.management.fileguard;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.eclipse.jgit.diff.RawText;
import org.eclipse.jgit.diff.RawTextComparator;
import org.eclipse.jgit.merge.MergeAlgorithm;
import org.eclipse.jgit.merge.MergeFormatter;
import org.eclipse.jgit.merge.MergeResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * workspace 单文件纯内存三方文本合并服务。
 *
 * <p>输入依次为 Patch 生成时基线、确认时当前文本和 Patch 目标文本。该服务使用 JGit
 * MergeAlgorithm 识别重叠编辑，不要求 workspace 是 Git 仓库，也不执行任何文件读写。
 */
@Service
public class WorkspaceThreeWayMergeService {

    private static final Logger LOG = LoggerFactory.getLogger(WorkspaceThreeWayMergeService.class);
    private static final int MAX_TEXT_BYTES = 1024 * 1024;
    private static final String CONFLICT_BINARY_CONTENT = "BINARY_CONTENT_UNSUPPORTED";
    private static final String CONFLICT_CONTENT_TOO_LARGE = "CONTENT_TOO_LARGE";
    private static final String CONFLICT_OVERLAPPING_EDIT = "OVERLAPPING_EDIT";
    private static final List<String> MERGE_SEQUENCE_NAMES = List.of("BASE", "CURRENT", "PATCH");

    /**
     * 合并单个 UTF-8 文本文件；有重叠编辑时只返回冲突，不生成带冲突标记的文件正文。
     */
    public WorkspaceTextMergeResult merge(String baseContent, String currentContent, String proposedContent)
            throws IOException {
        byte[] baseBytes = bytes(baseContent);
        byte[] currentBytes = bytes(currentContent);
        byte[] proposedBytes = bytes(proposedContent);
        if (isTooLarge(baseBytes, currentBytes, proposedBytes)) {
            return WorkspaceTextMergeResult.conflict(CONFLICT_CONTENT_TOO_LARGE);
        }
        if (RawText.isBinary(baseBytes) || RawText.isBinary(currentBytes) || RawText.isBinary(proposedBytes)) {
            return WorkspaceTextMergeResult.conflict(CONFLICT_BINARY_CONTENT);
        }

        MergeResult<RawText> mergeResult = new MergeAlgorithm().merge(RawTextComparator.DEFAULT,
                new RawText(baseBytes), new RawText(currentBytes), new RawText(proposedBytes));
        if (mergeResult.containsConflicts()) {
            LOG.info("SkillFactory三方文本合并检测到重叠编辑, baseBytes={}, currentBytes={}, proposedBytes={}",
                    baseBytes.length, currentBytes.length, proposedBytes.length);
            return WorkspaceTextMergeResult.conflict(CONFLICT_OVERLAPPING_EDIT);
        }

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        new MergeFormatter().formatMerge(output, mergeResult, MERGE_SEQUENCE_NAMES, StandardCharsets.UTF_8);
        return WorkspaceTextMergeResult.merged(output.toString(StandardCharsets.UTF_8));
    }

    private byte[] bytes(String content) {
        return content == null ? new byte[0] : content.getBytes(StandardCharsets.UTF_8);
    }

    private boolean isTooLarge(byte[]... contents) {
        for (byte[] content : contents) {
            if (content.length > MAX_TEXT_BYTES) {
                return true;
            }
        }
        return false;
    }
}
