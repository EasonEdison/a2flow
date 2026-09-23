package dev.a2flow.management.lifecycle.artifact;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/**
 * SkillFactory 工作区下载 ZIP 的纯文件归档组件。
 *
 * <p>上游生命周期服务负责解析受控 workspace view 和筛选可导出文件；本组件只把这些文件以 workspace
 * 相对路径写入内存 ZIP，并返回页面下载所需的文件名和字节。它不创建发布产物、不写数据库、不修改
 * workspace，也不改变正式发布 ZIP 必须带 `skillCode/` 顶层目录的独立契约。
 */
public final class WorkspaceZipArchive {

    private static final String ZIP_SUFFIX = ".zip";
    private static final String ZIP_ENTRY_SEPARATOR = "/";
    private static final String ERROR_SKILL_CODE_INVALID = "skillCode is invalid";
    private static final String ERROR_WORKSPACE_INVALID = "workspace is invalid";
    private static final String ERROR_EXPORT_EMPTY = "workspace export is empty";
    private static final String ERROR_EXPORT_FILE_INVALID = "workspace export file is invalid";
    private static final String ERROR_EXPORT_SYMBOLIC_LINK = "workspace export symbolic link is not allowed";
    private static final String ERROR_EXPORT_FILE_OUTSIDE_WORKSPACE = "workspace export file outside workspace";
    private static final String ERROR_EXPORT_TOO_LARGE = "workspace export is too large";
    private static final long DETERMINISTIC_ZIP_ENTRY_TIME = 0L;
    private static final long MAX_EXPORT_SOURCE_BYTES = 100L * 1024L * 1024L;

    private WorkspaceZipArchive() {
    }

    /**
     * 使用 workspace 内相对路径生成扁平根目录 ZIP。
     *
     * @param skillCode 下载文件名使用的不可变 Skill 标识
     * @param workspace 已经由生命周期服务解析并校验的 workspace view 根目录
     * @param files 已经过 Repository 扫描和业务文件类型筛选的文件
     */
    public static Export build(String skillCode, Path workspace, List<Path> files) throws IOException {
        String normalizedSkillCode = normalizeSkillCode(skillCode);
        Path normalizedWorkspace = normalizeWorkspace(workspace);
        if (files == null || files.isEmpty()) {
            throw new IllegalArgumentException(ERROR_EXPORT_EMPTY);
        }
        List<Path> sortedFiles = files.stream()
                .filter(Objects::nonNull)
                .map(Path::normalize)
                .sorted(Comparator.comparing(path -> relativePath(normalizedWorkspace, path)))
                .collect(Collectors.toList());
        if (sortedFiles.isEmpty()) {
            throw new IllegalArgumentException(ERROR_EXPORT_EMPTY);
        }
        validateFiles(normalizedWorkspace, sortedFiles);
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(output)) {
            for (Path file : sortedFiles) {
                ZipEntry entry = new ZipEntry(relativePath(normalizedWorkspace, file));
                entry.setTime(DETERMINISTIC_ZIP_ENTRY_TIME);
                zip.putNextEntry(entry);
                Files.copy(file, zip);
                zip.closeEntry();
            }
        }
        return new Export(normalizedSkillCode + ZIP_SUFFIX, output.toByteArray(), sortedFiles.size());
    }

    private static String normalizeSkillCode(String skillCode) {
        String normalized = skillCode == null ? "" : skillCode.trim();
        if (normalized.isEmpty() || normalized.contains(ZIP_ENTRY_SEPARATOR) || normalized.contains("\\")) {
            throw new IllegalArgumentException(ERROR_SKILL_CODE_INVALID);
        }
        return normalized;
    }

    private static Path normalizeWorkspace(Path workspace) {
        if (workspace == null) {
            throw new IllegalArgumentException(ERROR_WORKSPACE_INVALID);
        }
        Path normalized = workspace.normalize();
        if (!Files.isDirectory(normalized)) {
            throw new IllegalArgumentException(ERROR_WORKSPACE_INVALID);
        }
        return normalized;
    }

    private static void validateFiles(Path workspace, List<Path> files) throws IOException {
        long sourceBytes = 0L;
        for (Path file : files) {
            if (!file.startsWith(workspace)) {
                throw new IllegalArgumentException(ERROR_EXPORT_FILE_OUTSIDE_WORKSPACE);
            }
            if (Files.isSymbolicLink(file)) {
                throw new IllegalArgumentException(ERROR_EXPORT_SYMBOLIC_LINK);
            }
            if (!Files.isRegularFile(file)) {
                throw new IllegalArgumentException(ERROR_EXPORT_FILE_INVALID);
            }
            sourceBytes += Files.size(file);
            if (sourceBytes > MAX_EXPORT_SOURCE_BYTES) {
                throw new IllegalArgumentException(ERROR_EXPORT_TOO_LARGE);
            }
        }
    }

    private static String relativePath(Path workspace, Path file) {
        String relative = workspace.relativize(file).normalize().toString().replace('\\', '/');
        if (relative.isEmpty() || relative.equals("..") || relative.startsWith("../")) {
            throw new IllegalArgumentException(ERROR_EXPORT_FILE_OUTSIDE_WORKSPACE);
        }
        return relative;
    }

    /**
     * 页面下载所需的不可变 ZIP 结果。
     */
    public static final class Export {

        private final String zipFileName;
        private final byte[] zipBytes;
        private final int fileCount;

        private Export(String zipFileName, byte[] zipBytes, int fileCount) {
            this.zipFileName = zipFileName;
            this.zipBytes = zipBytes.clone();
            this.fileCount = fileCount;
        }

        public String getZipFileName() {
            return zipFileName;
        }

        public byte[] getZipBytes() {
            return zipBytes.clone();
        }

        public int getFileCount() {
            return fileCount;
        }
    }
}
