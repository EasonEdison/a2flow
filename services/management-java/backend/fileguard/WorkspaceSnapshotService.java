package dev.a2flow.management.fileguard;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import com.google.common.collect.Lists;
import com.google.common.collect.Maps;
import dev.a2flow.management.config.WorkspaceChangeGuardConfig;
import dev.a2flow.management.storage.db.repository
        .SkillFactoryWorkspaceFileRepository;

/**
 * SkillFactory workspace 文件快照服务。
 *
 * <p>该服务复用文件 Repository 生成的 canonical 快照，并提供逐文件 diff 和当前内容短预览。
 * AI Coding 只负责在模型调用前和 patch confirm 前调用它；生命周期、验证和发布复用同一摘要事实。
 * 该服务不感知模型、不写 observation、不修改任何 workspace 文件。
 */
@Service
public class WorkspaceSnapshotService {

    private static final String PATH_SEPARATOR = "/";
    private static final String PREVIEW_DELETED = "[deleted]";
    private static final String PREVIEW_UNREADABLE = "[unreadable]";

    @Resource
    private SkillFactoryWorkspaceFileRepository workspaceFileRepository;

    /**
     * 采集指定目录的文件树快照。
     */
    public WorkspaceSnapshot capture(Path workspaceDir) throws IOException {
        Path root = workspaceDir.toAbsolutePath().normalize();
        return workspaceFileRepository.captureWorkspaceSnapshot(root);
    }

    /**
     * 计算两个快照之间的文件级差异。
     */
    public WorkspaceSnapshotDiff diff(WorkspaceSnapshot previous, WorkspaceSnapshot current) {
        WorkspaceSnapshotDiff diff = new WorkspaceSnapshotDiff();
        Map<String, String> previousFiles = previous == null ? Maps.newHashMap() : previous.safeFileDigestMap();
        Map<String, String> currentFiles = current == null ? Maps.newHashMap() : current.safeFileDigestMap();
        for (Map.Entry<String, String> currentFile : currentFiles.entrySet()) {
            String path = currentFile.getKey();
            if (!previousFiles.containsKey(path)) {
                diff.getAddedFiles().add(path);
            } else if (!StringUtils.equals(previousFiles.get(path), currentFile.getValue())) {
                diff.getModifiedFiles().add(path);
            }
        }
        for (String path : previousFiles.keySet()) {
            if (!currentFiles.containsKey(path)) {
                diff.getDeletedFiles().add(path);
            }
        }
        sortPaths(diff.getAddedFiles());
        sortPaths(diff.getModifiedFiles());
        sortPaths(diff.getDeletedFiles());
        return diff;
    }

    /**
     * 从快照中提取指定文件的摘要，用于 patch 草稿记录 touched-file CAS 证据。
     */
    public Map<String, String> fileDigestMapForPaths(WorkspaceSnapshot snapshot, List<String> paths) {
        Map<String, String> result = Maps.newLinkedHashMap();
        if (snapshot == null || CollectionUtils.isEmpty(paths)) {
            return result;
        }
        Map<String, String> fileDigestMap = snapshot.safeFileDigestMap();
        for (String path : paths) {
            String normalizedPath = normalizeRelativePath(path);
            result.put(normalizedPath, StringUtils.defaultString(fileDigestMap.get(normalizedPath)));
        }
        return result;
    }

    /**
     * 读取指定快照对应的文件文本，作为 Patch 三方合并基线。
     *
     * <p>读取前后都以快照中的逐文件摘要校验，避免采集快照与保存基线之间发生并发修改。
     * 不存在的文件以显式 null 保存，用于区分 ADD 与空文件。
     */
    public Map<String, String> fileContentMapForPaths(Path workspaceDir, WorkspaceSnapshot snapshot,
            List<String> paths) throws IOException {
        Map<String, String> result = Maps.newLinkedHashMap();
        if (snapshot == null || CollectionUtils.isEmpty(paths)) {
            return result;
        }
        Path root = workspaceDir.toAbsolutePath().normalize();
        Map<String, String> fileDigestMap = snapshot.safeFileDigestMap();
        for (String path : paths) {
            String normalizedPath = normalizeRelativePath(path);
            Path file = root.resolve(normalizedPath).toAbsolutePath().normalize();
            if (!file.startsWith(root)) {
                throw new IllegalArgumentException("Path outside workspace: " + normalizedPath);
            }
            String expectedDigest = fileDigestMap.get(normalizedPath);
            if (StringUtils.isBlank(expectedDigest)) {
                if (Files.exists(file)) {
                    throw new IllegalStateException("workspace changed while capturing patch base: "
                            + normalizedPath);
                }
                result.put(normalizedPath, null);
                continue;
            }
            if (!Files.isRegularFile(file)
                    || Files.size(file) > SkillFactoryWorkspaceFileRepository.MAX_TEXT_FILE_BYTES) {
                throw new IllegalStateException("patch base is not a supported text file: " + normalizedPath);
            }
            byte[] content = Files.readAllBytes(file);
            if (!StringUtils.equals(expectedDigest, workspaceFileRepository.sha256(content))) {
                throw new IllegalStateException("workspace changed while capturing patch base: "
                        + normalizedPath);
            }
            result.put(normalizedPath, new String(content, StandardCharsets.UTF_8));
        }
        return result;
    }

    /**
     * 生成给模型看的短摘要，避免把完整文件内容注入上下文。
     */
    public String buildModelVisibleSummary(Path workspaceDir, WorkspaceSnapshotDiff diff,
            WorkspaceChangeGuardConfig config) {
        if (diff == null || !diff.hasChange()) {
            return StringUtils.EMPTY;
        }
        WorkspaceChangeGuardConfig safeConfig = config == null ? new WorkspaceChangeGuardConfig() : config;
        List<String> changedPaths = changedPaths(diff);
        int maxFiles = safeConfig.safeMaxChangedFilesInSummary();
        StringBuilder builder = new StringBuilder();
        builder.append("检测到 workspace 文件自模型上一份已读快照后发生变化：")
                .append("新增 ").append(diff.getAddedFiles().size()).append(" 个，")
                .append("修改 ").append(diff.getModifiedFiles().size()).append(" 个，")
                .append("删除 ").append(diff.getDeletedFiles().size()).append(" 个。");
        builder.append("请先重新读取受影响文件，再继续生成或修改 patch。");
        builder.append("受影响文件：")
                .append(StringUtils.join(changedPaths.stream().limit(maxFiles).collect(Collectors.toList()), ", "));
        if (changedPaths.size() > maxFiles) {
            builder.append(" 等 ").append(changedPaths.size()).append(" 个。");
        }
        if (safeConfig.isIncludeChangedFilePreview()) {
            appendFilePreviews(builder, workspaceDir, changedPaths, maxFiles, safeConfig.safeMaxFilePreviewChars());
        }
        return builder.toString();
    }

    public List<String> changedPaths(WorkspaceSnapshotDiff diff) {
        List<String> result = Lists.newArrayList();
        if (diff == null) {
            return result;
        }
        result.addAll(diff.getAddedFiles());
        result.addAll(diff.getModifiedFiles());
        result.addAll(diff.getDeletedFiles());
        sortPaths(result);
        return result;
    }

    private void appendFilePreviews(StringBuilder builder, Path workspaceDir, List<String> changedPaths,
            int maxFiles, int maxChars) {
        if (CollectionUtils.isEmpty(changedPaths)) {
            return;
        }
        Path root = workspaceDir.toAbsolutePath().normalize();
        builder.append(" 变更文件短预览：");
        for (String relativePath : changedPaths.stream().limit(maxFiles).collect(Collectors.toList())) {
            builder.append("\n- ").append(relativePath).append(": ")
                    .append(readPreview(root, relativePath, maxChars));
        }
    }

    private String readPreview(Path root, String relativePath, int maxChars) {
        try {
            Path path = root.resolve(normalizeRelativePath(relativePath)).toAbsolutePath().normalize();
            if (!path.startsWith(root)) {
                return PREVIEW_UNREADABLE;
            }
            if (!Files.exists(path)) {
                return PREVIEW_DELETED;
            }
            if (!Files.isRegularFile(path)) {
                return PREVIEW_UNREADABLE;
            }
            String text = Files.readString(path, StandardCharsets.UTF_8)
                    .replaceAll("\\s+", " ")
                    .trim();
            return StringUtils.abbreviate(text, maxChars);
        } catch (Exception e) {
            return PREVIEW_UNREADABLE;
        }
    }

    private String normalizeRelativePath(String path) {
        return StringUtils.defaultString(path).replace("\\", PATH_SEPARATOR);
    }

    private void sortPaths(List<String> paths) {
        if (paths != null) {
            paths.sort(String::compareTo);
        }
    }
}
