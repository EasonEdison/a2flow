package dev.a2flow.management.lifecycle.artifact;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.SkillFactoryValidationException;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceFileRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory Skill ZIP 产物服务。
 *
 * <p>该服务只负责把 workspace 构建成 ZIP、校验 ZIP 结构和把 ZIP 安全恢复到受控 workspace。
 * ZIP 元数据由共享发布控制面的 {@link ReleaseArtifact} 保存，不再写入独立 `skill_version` 表。
 */
@Service
@Slf4j
public class SkillPackageArtifactService {

    public static final String ARTIFACT_TYPE_SKILL_ZIP = "SKILL_ZIP";
    public static final String STORAGE_PROVIDER_LOCAL = "LOCAL";
    private static final String ZIP_SUFFIX = ".zip";
    private static final String ZIP_ENTRY_SEPARATOR = "/";
    private static final String RESTORE_TEMP_DIR = "_restore";
    private static final String RESTORE_UNZIP_DIR = "_unzip";
    private static final String MACOS_RESOURCE_DIR_PREFIX = "__MACOSX/";
    private static final String GIT_DIR_PREFIX = ".git/";
    private static final String GIT_DIR_SEGMENT = "/.git/";
    private static final String PYTHON_CACHE_PREFIX = "__pycache__/";
    private static final String PYTHON_CACHE_SEGMENT = "/__pycache__/";
    private static final String DS_STORE_SUFFIX = ".DS_Store";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_FILE_COUNT = "fileCount";
    private static final String FIELD_ZIP_FILE_NAME = "zipFileName";
    private static final String FIELD_LOCAL_BUILD = "localBuild";
    private static final String ERROR_PACKAGE_FILE_NOT_FOUND = "package file does not exist";
    private static final String ERROR_PACKAGE_DOWNLOAD_TOO_LARGE = "package download is too large";
    private static final String ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE = "restore path outside workspace";
    private static final String ERROR_ZIP_PACKAGE_EMPTY = "zip package is empty";
    private static final String ERROR_UPLOAD_ZIP_EMPTY = "zip content is empty";
    private static final String ERROR_UPLOAD_ZIP_TOO_LARGE = "zip content is too large";
    private static final String ERROR_UPLOAD_ZIP_FILE_NAME_INVALID = "zipFileName must be zip";
    private static final String ERROR_UPLOAD_ZIP_NAME_NOT_MATCH_SKILL_CODE =
            "zipFileName must match skillCode";
    private static final String ERROR_RELEASE_WORKSPACE_NOT_FOUND = "release workspace does not exist";
    private static final String ERROR_HISTORICAL_PACKAGE_NOT_FOUND = "historical package does not exist";
    private static final String ERROR_RELEASE_PACKAGE_ROOT_INVALID = "Skill发布ZIP顶层目录必须等于skillCode";
    private static final String ERROR_RELEASE_PACKAGE_SKILL_MD_MISSING = "Skill发布ZIP缺少skillCode/SKILL.md";
    private static final String ERROR_RELEASE_PACKAGE_PATH_INVALID = "Skill发布ZIP包含不安全路径";
    private static final String PATH_PARENT_SEGMENT = "..";
    private static final String PATH_PARENT_PREFIX = "../";
    private static final String PATH_PARENT_SUFFIX = "/..";
    private static final String PATH_PARENT_MIDDLE = "/../";
    private static final String WINDOWS_DRIVE_SEPARATOR = ":/";
    private static final int WINDOWS_DRIVE_SEPARATOR_INDEX = 1;
    private static final long DETERMINISTIC_ZIP_ENTRY_TIME = 0L;

    private static final long MAX_PACKAGE_BYTES = 100L * 1024L * 1024L;
    private static final int RESTORE_BUFFER_SIZE = 8192;

    @Value("${A2FLOW_PACKAGE_MAX_EXPANDED_BYTES:33554432}")
    private long maxExpandedBytes = 33554432L;
    @Value("${A2FLOW_PACKAGE_MAX_ENTRY_BYTES:8388608}")
    private long maxEntryBytes = 8388608L;
    @Value("${A2FLOW_PACKAGE_MAX_ENTRIES:2000}")
    private int maxEntries = 2000;

    @Resource
    private SkillFactoryWorkspaceFileRepository fileRepository;

    @Resource
    private DatabaseArtifactService databaseArtifacts;

    /** 从当前 workspace 构建 ZIP，并返回可保存到共享发布状态的结构化产物。 */
    public ReleaseArtifact buildPackage(SkillDraft draft, Path buildDir, Path workspace,
            List<Path> packageFiles) throws IOException {
        return buildPackage(draft, buildDir, workspace, defaultZipFileName(draft, workspace), packageFiles);
    }

    /**
     * 从指定源码目录构建指定文件名的 ZIP。
     *
     * <p>临时目录用于构建，完成后将不可变字节保存至数据库。这里不推进发布状态；调用方仍需把返回的
     * {@link ReleaseArtifact} 关联到共享 ReleaseBuild 或 ReleaseVersion，Runtime 发布单独验证。
     */
    public ReleaseArtifact buildPackage(SkillDraft draft, Path buildDir, Path workspace, String zipFileName,
            List<Path> packageFiles) throws IOException {
        log.info("SkillFactory开始构建工作区ZIP, workspaceId:{}, workspacePath:{}, fileCount:{}",
                draft.getWorkspaceId(), workspace, packageFiles.size());
        Path zipPath = buildZip(buildDir, workspace, zipFileName,
                StringUtils.defaultIfBlank(draft.getSkillCode(), workspace.getFileName().toString()),
                packageFiles);
        ReleaseArtifact artifact = new ReleaseArtifact()
                .setArtifactType(ARTIFACT_TYPE_SKILL_ZIP)
                .setStorageProvider(STORAGE_PROVIDER_LOCAL)
                .setObjectKey(StringUtils.EMPTY)
                .setPackageUrl(zipPath.toUri().toString())
                .setPackageDigest(fileRepository.sha256(Files.readAllBytes(zipPath)))
                .setFileTreeDigest(draft.getFileTreeDigest())
                .setSize(Files.size(zipPath))
                .setBuildSummary(buildSummaryJson(draft, packageFiles.size(), zipPath));
        log.info("SkillFactory工作区ZIP构建完成, workspaceId:{}, zipPath:{}, digest:{}, bytes:{}",
                draft.getWorkspaceId(), zipPath, artifact.getPackageDigest(), artifact.getSize());
        return databaseArtifacts.save(draft.getWorkspaceId(), Files.readAllBytes(zipPath), artifact);
    }

    /**
     * 构建页面下载使用的扁平工作区 ZIP。
     *
     * <p>下载 ZIP 以 workspace view 为相对路径根，不带 `skillCode/` 上级目录；正式发布 ZIP 继续走
     * `buildPackage`，两种产物语义不混用。
     */
    public WorkspaceZipArchive.Export buildWorkspaceExport(
            String skillCode, Path workspace, List<Path> exportFiles) throws IOException {
        log.info("SkillFactory开始导出工作区ZIP, skillCode:{}, workspacePath:{}, fileCount:{}",
                skillCode, workspace, exportFiles == null ? 0 : exportFiles.size());
        WorkspaceZipArchive.Export export = WorkspaceZipArchive.build(skillCode, workspace, exportFiles);
        log.info("SkillFactory工作区ZIP导出完成, skillCode:{}, zipFileName:{}, fileCount:{}, bytes:{}",
                skillCode, export.getZipFileName(), export.getFileCount(), export.getZipBytes().length);
        return export;
    }

    /**
     * 从历史正式目录和 ZIP 读取结构化产物，不创建版本。
     */
    public ReleaseArtifact describeHistoricalPackage(SkillDraft draft, Path releaseWorkspace, Path packagePath)
            throws IOException {
        if (!Files.isDirectory(releaseWorkspace)) {
            log.warn("SkillFactory读取历史版本失败，正式版本目录不存在, workspaceId:{}, path:{}",
                    draft.getWorkspaceId(), releaseWorkspace);
            throw new IllegalArgumentException(ERROR_RELEASE_WORKSPACE_NOT_FOUND);
        }
        if (!Files.isRegularFile(packagePath)) {
            log.warn("SkillFactory读取历史版本失败，正式版本ZIP不存在, workspaceId:{}, path:{}",
                    draft.getWorkspaceId(), packagePath);
            throw new IllegalArgumentException(ERROR_HISTORICAL_PACKAGE_NOT_FOUND);
        }
        ReleaseArtifact artifact = new ReleaseArtifact()
                .setArtifactType(ARTIFACT_TYPE_SKILL_ZIP)
                .setStorageProvider(STORAGE_PROVIDER_LOCAL)
                .setPackageUrl(packagePath.toUri().toString())
                .setPackageDigest(fileRepository.sha256(Files.readAllBytes(packagePath)))
                .setFileTreeDigest(fileRepository.digestWorkspace(releaseWorkspace))
                .setSize(Files.size(packagePath));
        log.info("SkillFactory读取历史ZIP产物完成, workspaceId:{}, packagePath:{}, packageDigest:{}",
                draft.getWorkspaceId(), packagePath, artifact.getPackageDigest());
        return artifact;
    }

    /**
     * 读取并校验准备上传 LangBridge 的正式 ZIP。
     *
     * <p>所有有效文件必须位于 {@code skillCode/} 顶层目录下，并且至少包含
     * {@code skillCode/SKILL.md}。校验发生在对象存储上传前，避免把不满足 agent-service 下载约束的包
     * 发送到外部平台。
     */
    public byte[] readValidatedReleasePackage(Path packagePath, String skillCode) throws IOException {
        if (!Files.isRegularFile(packagePath)) {
            throw new IllegalArgumentException(ERROR_PACKAGE_FILE_NOT_FOUND);
        }
        byte[] bytes = Files.readAllBytes(packagePath);
        if (bytes.length <= 0) {
            throw new IllegalArgumentException(ERROR_ZIP_PACKAGE_EMPTY);
        }
        String rootPrefix = skillCode + ZIP_ENTRY_SEPARATOR;
        String requiredSkillMd = rootPrefix + "SKILL.md";
        boolean skillMdFound = false;
        int fileCount = 0;
        ExtractionBudget budget = extractionBudget();
        try (ZipInputStream input = new ZipInputStream(new ByteArrayInputStream(bytes))) {
            ZipEntry entry;
            while ((entry = input.getNextEntry()) != null) {
                budget.nextEntry();
                String rawEntryName = StringUtils.defaultString(entry.getName()).replace('\\', '/');
                if (isUnsafeReleaseEntry(rawEntryName)) {
                    log.warn("SkillFactory发布ZIP包含不安全路径, skillCode:{}, entry:{}",
                            skillCode, rawEntryName);
                    throw new IllegalArgumentException(ERROR_RELEASE_PACKAGE_PATH_INVALID);
                }
                String entryName = StringUtils.stripStart(rawEntryName, ZIP_ENTRY_SEPARATOR);
                if (StringUtils.isBlank(entryName) || isIgnoredZipRelativePath(entryName)) {
                    budget.copyEntry(input, OutputStream.nullOutputStream());
                    input.closeEntry();
                    continue;
                }
                if (!StringUtils.equals(entryName, skillCode) && !StringUtils.startsWith(entryName, rootPrefix)) {
                    log.warn("SkillFactory发布ZIP顶层目录非法, skillCode:{}, entry:{}", skillCode, entryName);
                    throw new IllegalArgumentException(ERROR_RELEASE_PACKAGE_ROOT_INVALID);
                }
                if (!entry.isDirectory()) {
                    fileCount++;
                    skillMdFound = skillMdFound || StringUtils.equals(entryName, requiredSkillMd);
                }
                budget.copyEntry(input, OutputStream.nullOutputStream());
                input.closeEntry();
            }
        }
        if (fileCount <= 0) {
            throw new IllegalArgumentException(ERROR_ZIP_PACKAGE_EMPTY);
        }
        if (!skillMdFound) {
            log.warn("SkillFactory发布ZIP缺少SKILL.md, skillCode:{}, requiredEntry:{}",
                    skillCode, requiredSkillMd);
            throw new IllegalArgumentException(ERROR_RELEASE_PACKAGE_SKILL_MD_MISSING);
        }
        log.info("SkillFactory发布ZIP结构校验通过, skillCode:{}, fileCount:{}, bytes:{}",
                skillCode, fileCount, bytes.length);
        return bytes;
    }

    private boolean isUnsafeReleaseEntry(String entryName) {
        return StringUtils.startsWith(entryName, ZIP_ENTRY_SEPARATOR)
                || StringUtils.equals(entryName, PATH_PARENT_SEGMENT)
                || StringUtils.startsWith(entryName, PATH_PARENT_PREFIX)
                || StringUtils.endsWith(entryName, PATH_PARENT_SUFFIX)
                || StringUtils.contains(entryName, PATH_PARENT_MIDDLE)
                || StringUtils.indexOf(entryName, WINDOWS_DRIVE_SEPARATOR) == WINDOWS_DRIVE_SEPARATOR_INDEX;
    }

    /** Legacy caller-selected URLs/files cannot establish artifact ownership or integrity. */
    public int restorePackage(Path workspaceRoot, Path workspace, String packageUrl, String... rootDirNames)
            throws IOException {
        throw SkillFactoryValidationException.packageRestoreSourceRequired();
    }

    /**
     * 从已经通过数据库归属与摘要校验的不可变 ZIP 恢复 workspace。
     *
     * <p>ZIP 从已加载字节流式解压至临时目录，完成展开限额、路径、空包和根目录校验，
     * 成功后才替换目标 workspace；调用方负责在进入本方法前校验 Build artifact 摘要。
     */
    public int restoreImmutablePackage(Path workspaceRoot, Path workspace, byte[] zipBytes,
            String... rootDirNames) throws IOException {
        if (zipBytes == null || zipBytes.length == 0) {
            throw new IllegalArgumentException(ERROR_ZIP_PACKAGE_EMPTY);
        }
        if (zipBytes.length > MAX_PACKAGE_BYTES) {
            throw new IllegalArgumentException(ERROR_PACKAGE_DOWNLOAD_TOO_LARGE);
        }
        Path normalizedWorkspaceRoot = workspaceRoot.normalize();
        Path normalizedWorkspace = workspace.normalize();
        if (!normalizedWorkspace.startsWith(normalizedWorkspaceRoot)) {
            throw new IllegalArgumentException(ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE);
        }
        Path tempBaseDir = createRestoreDirectory(normalizedWorkspaceRoot, workspace.getFileName().toString());
        Path unzipDir = tempBaseDir.resolve(RESTORE_UNZIP_DIR);
        try {
            int restoredFileCount = unzipToTemp(zipBytes, unzipDir, rootDirNames);
            if (restoredFileCount <= 0) {
                throw new IllegalArgumentException(ERROR_ZIP_PACKAGE_EMPTY);
            }
            replaceWorkspace(normalizedWorkspace, unzipDir);
            log.info("SkillFactory不可变Build ZIP恢复完成, workspace:{}, restoredFileCount:{}, bytes:{}",
                    normalizedWorkspace, restoredFileCount, zipBytes.length);
            return restoredFileCount;
        } finally {
            deleteRecursivelyIfExists(tempBaseDir);
        }
    }

    /**
     * 把页面上传的源码 ZIP 导入到当前 workspace。
     *
     * <p>页面上传 ZIP 是创建/编辑入口，不是最终发布包。从已有字节直接有界解压到临时目录，
     * 校验完成后才替换 workspace；压缩包不再重复落盘。
     */
    public int importUploadedZip(Path workspaceRoot, Path workspace, String skillCode, String zipFileName,
            byte[] zipBytes) throws IOException {
        validateUploadZip(zipFileName, zipBytes, skillCode);
        Path normalizedWorkspaceRoot = workspaceRoot.normalize();
        Path normalizedWorkspace = workspace.normalize();
        if (!normalizedWorkspace.startsWith(normalizedWorkspaceRoot)) {
            log.warn("SkillFactory导入ZIP失败，workspace路径越界, workspaceRoot:{}, workspace:{}",
                    normalizedWorkspaceRoot, normalizedWorkspace);
            throw new IllegalArgumentException(ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE);
        }
        Path tempBaseDir = createRestoreDirectory(normalizedWorkspaceRoot, workspace.getFileName().toString());
        Path unzipDir = tempBaseDir.resolve(RESTORE_UNZIP_DIR);
        try {
            log.info("SkillFactory开始解压导入ZIP, workspace:{}, skillCode:{}, zipFileName:{}, zipBytes:{}",
                    normalizedWorkspace, skillCode, zipFileName, zipBytes.length);
            int importedFileCount = unzipToTemp(zipBytes, unzipDir, workspace.getFileName().toString(),
                    StringUtils.defaultString(skillCode), stripZipSuffix(zipFileName));
            if (importedFileCount <= 0) {
                log.warn("SkillFactory导入ZIP失败，ZIP为空, workspace:{}, zipFileName:{}",
                        normalizedWorkspace, zipFileName);
                throw new IllegalArgumentException(ERROR_ZIP_PACKAGE_EMPTY);
            }
            Path normalizedImportDir = normalizeSingleTopLevelDir(unzipDir);
            replaceWorkspace(normalizedWorkspace, normalizedImportDir);
            log.info("SkillFactory导入ZIP完成, workspace:{}, zipFileName:{}, importedFileCount:{}",
                    normalizedWorkspace, zipFileName, importedFileCount);
            return importedFileCount;
        } finally {
            deleteRecursivelyIfExists(tempBaseDir);
        }
    }

    private Path buildZip(Path buildDir, Path workspace, String zipFileName, String rootDirName,
            List<Path> packageFiles)
            throws IOException {
        Files.createDirectories(buildDir);
        String normalizedZipFileName = StringUtils.endsWithIgnoreCase(zipFileName, ZIP_SUFFIX)
                ? zipFileName : zipFileName + ZIP_SUFFIX;
        Path zipPath = buildDir.resolve(normalizedZipFileName).normalize();
        if (!zipPath.startsWith(buildDir.normalize())) {
            log.warn("SkillFactory构建ZIP失败，zip文件名越界, buildDir:{}, zipFileName:{}",
                    buildDir, zipFileName);
            throw new IllegalArgumentException(ERROR_UPLOAD_ZIP_FILE_NAME_INVALID);
        }
        try (ZipOutputStream zipOutputStream = new ZipOutputStream(Files.newOutputStream(zipPath))) {
            List<Path> sortedPackageFiles = packageFiles.stream()
                    .sorted(Comparator.comparing(path -> normalize(workspace.relativize(path))))
                    .collect(Collectors.toList());
            for (Path path : sortedPackageFiles) {
                String relativePath = normalize(workspace.relativize(path));
                ZipEntry entry = new ZipEntry(rootDirName + ZIP_ENTRY_SEPARATOR + relativePath);
                entry.setTime(DETERMINISTIC_ZIP_ENTRY_TIME);
                zipOutputStream.putNextEntry(entry);
                Files.copy(path, zipOutputStream);
                zipOutputStream.closeEntry();
            }
        }
        return zipPath;
    }

    private Path createRestoreDirectory(Path workspaceRoot, String workspaceName) throws IOException {
        Path restoreRoot = workspaceRoot.resolve(RESTORE_TEMP_DIR);
        Files.createDirectories(restoreRoot);
        // Atomic unique directory: concurrent failures cannot clean another request's files.
        return Files.createTempDirectory(restoreRoot, workspaceName + "-");
    }

    private int unzipToTemp(byte[] zipBytes, Path tempDir, String... rootDirNames) throws IOException {
        Files.createDirectories(tempDir);
        int restoredFileCount = 0;
        ExtractionBudget budget = extractionBudget();
        try (ZipInputStream input = new ZipInputStream(new ByteArrayInputStream(zipBytes))) {
            ZipEntry entry;
            while ((entry = input.getNextEntry()) != null) {
                budget.nextEntry();
                String relativePath = restoreRelativePath(entry.getName(), rootDirNames);
                if (StringUtils.isBlank(relativePath) || isIgnoredZipRelativePath(relativePath)) {
                    budget.copyEntry(input, OutputStream.nullOutputStream());
                    input.closeEntry();
                    continue;
                }
                Path target = tempDir.resolve(relativePath).normalize();
                if (!target.startsWith(tempDir)) {
                    throw new IllegalArgumentException(ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE);
                }
                if (entry.isDirectory()) {
                    Files.createDirectories(target);
                    budget.copyEntry(input, OutputStream.nullOutputStream());
                } else {
                    Files.createDirectories(target.getParent());
                    try (OutputStream output = Files.newOutputStream(target)) {
                        budget.copyEntry(input, output);
                    }
                    restoredFileCount++;
                }
                input.closeEntry();
            }
        }
        return restoredFileCount;
    }

    @PostConstruct
    void validateExtractionLimits() {
        if (maxExpandedBytes <= 0 || maxEntryBytes <= 0 || maxEntryBytes > maxExpandedBytes || maxEntries <= 0) {
            throw new IllegalArgumentException("PACKAGE_EXTRACTION_LIMITS_INVALID");
        }
    }

    private ExtractionBudget extractionBudget() {
        validateExtractionLimits();
        return new ExtractionBudget(maxExpandedBytes, maxEntryBytes, maxEntries);
    }

    /** Count actual streamed bytes, including ignored and directory payloads. */
    private static final class ExtractionBudget {
        private final long maxTotal;
        private final long maxEntry;
        private final int maxCount;
        private long total;
        private int entries;

        private ExtractionBudget(long maxTotal, long maxEntry, int maxCount) {
            this.maxTotal = maxTotal;
            this.maxEntry = maxEntry;
            this.maxCount = maxCount;
        }

        private void nextEntry() {
            if (entries >= maxCount) {
                throw SkillFactoryValidationException.packageLimitExceeded("PACKAGE_ENTRY_COUNT_EXCEEDED");
            }
            entries++;
        }

        private void copyEntry(InputStream input, OutputStream output) throws IOException {
            long entryBytes = 0;
            byte[] buffer = new byte[RESTORE_BUFFER_SIZE];
            int length;
            while ((length = input.read(buffer)) != -1) {
                if (length > maxEntry - entryBytes) {
                    throw SkillFactoryValidationException.packageLimitExceeded("PACKAGE_ENTRY_BYTES_EXCEEDED");
                }
                if (length > maxTotal - total) {
                    throw SkillFactoryValidationException.packageLimitExceeded("PACKAGE_EXPANDED_BYTES_EXCEEDED");
                }
                entryBytes += length;
                total += length;
                output.write(buffer, 0, length);
            }
        }
    }

    private String restoreRelativePath(String entryName, String... rootDirNames) {
        String normalized = StringUtils.defaultString(entryName)
                .replace('\\', '/');
        normalized = StringUtils.stripStart(normalized, ZIP_ENTRY_SEPARATOR);
        if (StringUtils.isBlank(normalized)) {
            return StringUtils.EMPTY;
        }
        for (String rootDirName : rootDirNames) {
            if (StringUtils.isBlank(rootDirName)) {
                continue;
            }
            if (StringUtils.equals(normalized, rootDirName)) {
                return StringUtils.EMPTY;
            }
            String workspacePrefix = rootDirName + ZIP_ENTRY_SEPARATOR;
            if (StringUtils.startsWith(normalized, workspacePrefix)) {
                return normalized.substring(workspacePrefix.length());
            }
        }
        return normalized;
    }

    private void validateUploadZip(String zipFileName, byte[] zipBytes, String skillCode) {
        if (!StringUtils.endsWithIgnoreCase(zipFileName, ZIP_SUFFIX)) {
            log.warn("SkillFactory导入ZIP失败，文件名不是zip, zipFileName:{}", zipFileName);
            throw new IllegalArgumentException(ERROR_UPLOAD_ZIP_FILE_NAME_INVALID);
        }
        String zipSkillCode = stripZipSuffix(StringUtils.defaultString(zipFileName).trim());
        if (!StringUtils.equals(zipSkillCode, skillCode)) {
            log.warn("SkillFactory导入ZIP失败，zip文件名与skillCode不一致, zipFileName:{}, zipSkillCode:{}, "
                            + "skillCode:{}",
                    zipFileName, zipSkillCode, skillCode);
            throw new IllegalArgumentException(ERROR_UPLOAD_ZIP_NAME_NOT_MATCH_SKILL_CODE);
        }
        if (zipBytes == null || zipBytes.length <= 0) {
            log.warn("SkillFactory导入ZIP失败，上传内容为空, zipFileName:{}", zipFileName);
            throw new IllegalArgumentException(ERROR_UPLOAD_ZIP_EMPTY);
        }
        if (zipBytes.length > MAX_PACKAGE_BYTES) {
            log.warn("SkillFactory导入ZIP失败，上传内容过大, zipFileName:{}, bytes:{}, maxBytes:{}",
                    zipFileName, zipBytes.length, MAX_PACKAGE_BYTES);
            throw new IllegalArgumentException(ERROR_UPLOAD_ZIP_TOO_LARGE);
        }
    }

    private Path normalizeSingleTopLevelDir(Path unzipDir) throws IOException {
        try (Stream<Path> stream = Files.list(unzipDir)) {
            List<Path> children = stream.collect(Collectors.toList());
            if (children.size() == 1 && Files.isDirectory(children.get(0))) {
                Path child = children.get(0).normalize();
                if (child.startsWith(unzipDir)) {
                    log.info("SkillFactory导入ZIP检测到单一顶层目录，将作为workspace根目录, source:{}, target:{}",
                            unzipDir, child);
                    return child;
                }
            }
        }
        return unzipDir;
    }

    private boolean isIgnoredZipRelativePath(String relativePath) {
        String normalized = StringUtils.defaultString(relativePath).replace('\\', '/');
        return StringUtils.startsWith(normalized, MACOS_RESOURCE_DIR_PREFIX)
                || StringUtils.startsWith(normalized, GIT_DIR_PREFIX)
                || StringUtils.contains(normalized, GIT_DIR_SEGMENT)
                || StringUtils.startsWith(normalized, PYTHON_CACHE_PREFIX)
                || StringUtils.contains(normalized, PYTHON_CACHE_SEGMENT)
                || StringUtils.endsWith(normalized, DS_STORE_SUFFIX);
    }

    private String stripZipSuffix(String zipFileName) {
        return StringUtils.removeEndIgnoreCase(StringUtils.defaultString(zipFileName), ZIP_SUFFIX);
    }

    private String defaultZipFileName(SkillDraft draft, Path workspace) {
        String skillCode = draft == null ? StringUtils.EMPTY : draft.getSkillCode();
        return StringUtils.defaultIfBlank(skillCode, workspace.getFileName().toString()) + ZIP_SUFFIX;
    }

    private void replaceWorkspace(Path workspace, Path tempDir) throws IOException {
        Files.createDirectories(workspace.getParent());
        deleteRecursivelyIfExists(workspace);
        Files.move(tempDir, workspace, StandardCopyOption.REPLACE_EXISTING);
    }

    private void deleteRecursivelyIfExists(Path path) throws IOException {
        if (!Files.exists(path)) {
            return;
        }
        try (Stream<Path> stream = Files.walk(path)) {
            for (Path item : stream.sorted(Comparator.reverseOrder()).collect(Collectors.toList())) {
                Files.deleteIfExists(item);
            }
        }
    }

    private String buildSummaryJson(SkillDraft draft, int fileCount, Path zipPath) {
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put(FIELD_WORKSPACE_ID, draft.getWorkspaceId());
        summary.put(FIELD_FILE_COUNT, fileCount);
        summary.put(FIELD_ZIP_FILE_NAME, zipPath.getFileName().toString());
        summary.put(FIELD_LOCAL_BUILD, true);
        return JsonSupport.toJSON(summary);
    }

    private String normalize(Path path) {
        return path.normalize().toString().replace('\\', '/');
    }
}
