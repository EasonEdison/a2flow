package dev.a2flow.management.lifecycle.artifact;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URLConnection;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
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

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
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
    private static final String FILE_URI_SCHEME = "file";
    private static final String HTTP_URI_SCHEME = "http";
    private static final String HTTPS_URI_SCHEME = "https";
    private static final String RESTORE_TEMP_DIR = "_restore";
    private static final String RESTORE_DOWNLOAD_DIR = "_download";
    private static final String RESTORE_UNZIP_DIR = "_unzip";
    private static final String RESTORE_DOWNLOAD_FILE_NAME = "package.zip";
    private static final String RESTORE_TEMP_SEPARATOR = "-";
    private static final String IMPORT_TEMP_MARK = "import";
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
    private static final String ERROR_PACKAGE_URL_INVALID = "packageUrl is invalid";
    private static final String ERROR_PACKAGE_FILE_NOT_FOUND = "package file does not exist";
    private static final String ERROR_PACKAGE_FILE_OUTSIDE_WORKSPACE_ROOT = "package file outside workspace root";
    private static final String ERROR_PACKAGE_FILE_NOT_ZIP = "package file must be zip";
    private static final String ERROR_PACKAGE_URL_SCHEME_NOT_SUPPORTED = "packageUrl scheme is not supported";
    private static final String ERROR_PACKAGE_DOWNLOAD_EMPTY = "package download is empty";
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
    private static final int RESTORE_CONNECT_TIMEOUT_MS = 10_000;
    private static final int RESTORE_READ_TIMEOUT_MS = 60_000;
    private static final int RESTORE_BUFFER_SIZE = 8192;

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
        try (ZipInputStream input = new ZipInputStream(new ByteArrayInputStream(bytes))) {
            ZipEntry entry;
            while ((entry = input.getNextEntry()) != null) {
                String rawEntryName = StringUtils.defaultString(entry.getName()).replace('\\', '/');
                if (isUnsafeReleaseEntry(rawEntryName)) {
                    log.warn("SkillFactory发布ZIP包含不安全路径, skillCode:{}, entry:{}",
                            skillCode, rawEntryName);
                    throw new IllegalArgumentException(ERROR_RELEASE_PACKAGE_PATH_INVALID);
                }
                String entryName = StringUtils.stripStart(rawEntryName, ZIP_ENTRY_SEPARATOR);
                if (StringUtils.isBlank(entryName) || isIgnoredZipRelativePath(entryName)) {
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

    /**
     * 从 ZIP 包恢复 workspace 文件。
     *
     * <p>该方法支持两类包来源：一是 `PACKAGE_BUILD` 产生且位于 workspaceRoot 下的 `file://` 本地包；
     * 二是对象存储侧暴露的 HTTP/HTTPS ZIP URL。它只负责下载、ZIP entry 路径穿越校验和受控目录替换，
     * 不负责对象存储鉴权、发布审批或 LangBridge/OpenClaw 注册。
     */
    public int restorePackage(Path workspaceRoot, Path workspace, String packageUrl, String... rootDirNames)
            throws IOException {
        Path normalizedWorkspaceRoot = workspaceRoot.normalize();
        Path normalizedWorkspace = workspace.normalize();
        if (!normalizedWorkspace.startsWith(normalizedWorkspaceRoot)) {
            log.warn("SkillFactory包恢复失败，workspace路径越界, workspaceRoot:{}, workspace:{}",
                    normalizedWorkspaceRoot, normalizedWorkspace);
            throw new IllegalArgumentException(ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE);
        }
        Path tempBaseDir = normalizedWorkspaceRoot
                .resolve(RESTORE_TEMP_DIR)
                .resolve(workspace.getFileName() + RESTORE_TEMP_SEPARATOR + System.currentTimeMillis())
                .normalize();
        if (!tempBaseDir.startsWith(normalizedWorkspaceRoot)) {
            log.warn("SkillFactory包恢复失败，临时目录越界, workspaceRoot:{}, tempDir:{}",
                    normalizedWorkspaceRoot, tempBaseDir);
            throw new IllegalArgumentException(ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE);
        }
        Path unzipDir = tempBaseDir.resolve(RESTORE_UNZIP_DIR).normalize();
        if (!unzipDir.startsWith(tempBaseDir)) {
            log.warn("SkillFactory包恢复失败，解压目录越界, tempDir:{}, unzipDir:{}", tempBaseDir, unzipDir);
            throw new IllegalArgumentException(ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE);
        }
        int restoredFileCount = 0;
        try {
            Path zipPath = resolvePackageZip(normalizedWorkspaceRoot, tempBaseDir, packageUrl);
            restoredFileCount = unzipToTemp(zipPath, unzipDir, rootDirNames);
            if (restoredFileCount <= 0) {
                log.warn("SkillFactory包恢复失败，ZIP为空, zipPath:{}", zipPath);
                throw new IllegalArgumentException(ERROR_ZIP_PACKAGE_EMPTY);
            }
            replaceWorkspace(normalizedWorkspace, unzipDir);
            log.info("SkillFactory包恢复完成, workspace:{}, zipPath:{}, restoredFileCount:{}",
                    normalizedWorkspace, zipPath, restoredFileCount);
            return restoredFileCount;
        } finally {
            deleteRecursivelyIfExists(tempBaseDir);
        }
    }

    /**
     * 从已经通过受控对象存储客户端下载的不可变 ZIP 恢复 workspace。
     *
     * <p>ZIP 先完整写入 workspaceRoot 内临时目录并完成 entry 越界校验、空包校验和根目录剥离，
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
        Path tempBaseDir = normalizedWorkspaceRoot.resolve(RESTORE_TEMP_DIR)
                .resolve(workspace.getFileName() + RESTORE_TEMP_SEPARATOR + System.currentTimeMillis())
                .normalize();
        Path downloadDir = tempBaseDir.resolve(RESTORE_DOWNLOAD_DIR).normalize();
        Path unzipDir = tempBaseDir.resolve(RESTORE_UNZIP_DIR).normalize();
        if (!tempBaseDir.startsWith(normalizedWorkspaceRoot)
                || !downloadDir.startsWith(tempBaseDir) || !unzipDir.startsWith(tempBaseDir)) {
            throw new IllegalArgumentException(ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE);
        }
        try {
            Files.createDirectories(downloadDir);
            Path zipPath = downloadDir.resolve(RESTORE_DOWNLOAD_FILE_NAME).normalize();
            Files.write(zipPath, zipBytes);
            int restoredFileCount = unzipToTemp(zipPath, unzipDir, rootDirNames);
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
     * <p>页面上传 ZIP 是创建/编辑入口，不是最终发布包。这里会先把二进制内容写入 workspaceRoot 下的临时目录，
     * 再复用 ZIP entry 路径穿越校验和 workspace 替换逻辑，确保导入内容只能落到 SkillFactory 受控目录内。
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
        Path tempBaseDir = normalizedWorkspaceRoot
                .resolve(RESTORE_TEMP_DIR)
                .resolve(workspace.getFileName() + RESTORE_TEMP_SEPARATOR + IMPORT_TEMP_MARK
                        + RESTORE_TEMP_SEPARATOR + System.currentTimeMillis())
                .normalize();
        if (!tempBaseDir.startsWith(normalizedWorkspaceRoot)) {
            log.warn("SkillFactory导入ZIP失败，临时目录越界, workspaceRoot:{}, tempDir:{}",
                    normalizedWorkspaceRoot, tempBaseDir);
            throw new IllegalArgumentException(ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE);
        }
        Path downloadDir = tempBaseDir.resolve(RESTORE_DOWNLOAD_DIR).normalize();
        Path unzipDir = tempBaseDir.resolve(RESTORE_UNZIP_DIR).normalize();
        if (!downloadDir.startsWith(tempBaseDir) || !unzipDir.startsWith(tempBaseDir)) {
            log.warn("SkillFactory导入ZIP失败，临时子目录越界, tempDir:{}, downloadDir:{}, unzipDir:{}",
                    tempBaseDir, downloadDir, unzipDir);
            throw new IllegalArgumentException(ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE);
        }
        try {
            Files.createDirectories(downloadDir);
            Path zipPath = downloadDir.resolve(RESTORE_DOWNLOAD_FILE_NAME).normalize();
            Files.write(zipPath, zipBytes);
            log.info("SkillFactory开始解压导入ZIP, workspace:{}, skillCode:{}, zipFileName:{}, zipBytes:{}",
                    normalizedWorkspace, skillCode, zipFileName, zipBytes.length);
            int importedFileCount = unzipToTemp(zipPath, unzipDir, workspace.getFileName().toString(),
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

    private Path resolvePackageZip(Path workspaceRoot, Path tempBaseDir, String packageUrl) throws IOException {
        URI uri = parsePackageUri(packageUrl);
        String scheme = uri.getScheme();
        if (FILE_URI_SCHEME.equalsIgnoreCase(scheme)) {
            return resolveLocalZip(workspaceRoot, uri);
        }
        if (HTTP_URI_SCHEME.equalsIgnoreCase(scheme) || HTTPS_URI_SCHEME.equalsIgnoreCase(scheme)) {
            return downloadRemoteZip(tempBaseDir, uri);
        }
        log.warn("SkillFactory包恢复失败，不支持的packageUrl协议, scheme:{}, packageUrl:{}", scheme, packageUrl);
        throw new IllegalArgumentException(ERROR_PACKAGE_URL_SCHEME_NOT_SUPPORTED);
    }

    private URI parsePackageUri(String packageUrl) {
        try {
            URI uri = new URI(StringUtils.defaultString(packageUrl));
            if (StringUtils.isBlank(uri.getScheme())) {
                throw new IllegalArgumentException(ERROR_PACKAGE_URL_INVALID);
            }
            return uri;
        } catch (URISyntaxException e) {
            throw new IllegalArgumentException(ERROR_PACKAGE_URL_INVALID, e);
        }
    }

    private Path resolveLocalZip(Path workspaceRoot, URI uri) {
        Path zipPath = Paths.get(uri).normalize();
        if (!zipPath.startsWith(workspaceRoot)) {
            log.warn("SkillFactory包恢复失败，ZIP不在workspaceRoot下, workspaceRoot:{}, zipPath:{}",
                    workspaceRoot, zipPath);
            throw new IllegalArgumentException(ERROR_PACKAGE_FILE_OUTSIDE_WORKSPACE_ROOT);
        }
        if (!Files.isRegularFile(zipPath)) {
            log.warn("SkillFactory包恢复失败，ZIP不存在, zipPath:{}", zipPath);
            throw new IllegalArgumentException(ERROR_PACKAGE_FILE_NOT_FOUND);
        }
        if (!StringUtils.endsWithIgnoreCase(zipPath.getFileName().toString(), ZIP_SUFFIX)) {
            log.warn("SkillFactory包恢复失败，文件不是ZIP, zipPath:{}", zipPath);
            throw new IllegalArgumentException(ERROR_PACKAGE_FILE_NOT_ZIP);
        }
        return zipPath;
    }

    private Path downloadRemoteZip(Path tempBaseDir, URI uri) throws IOException {
        Path downloadDir = tempBaseDir.resolve(RESTORE_DOWNLOAD_DIR).normalize();
        if (!downloadDir.startsWith(tempBaseDir)) {
            log.warn("SkillFactory包恢复失败，下载目录越界, tempDir:{}, downloadDir:{}", tempBaseDir, downloadDir);
            throw new IllegalArgumentException(ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE);
        }
        Files.createDirectories(downloadDir);
        Path zipPath = downloadDir.resolve(RESTORE_DOWNLOAD_FILE_NAME).normalize();
        log.info("SkillFactory开始下载远端ZIP包, packageUrl:{}", uri);
        URLConnection connection = uri.toURL().openConnection();
        connection.setConnectTimeout(RESTORE_CONNECT_TIMEOUT_MS);
        connection.setReadTimeout(RESTORE_READ_TIMEOUT_MS);
        long downloadedBytes = 0L;
        byte[] buffer = new byte[RESTORE_BUFFER_SIZE];
        try (InputStream inputStream = connection.getInputStream();
                OutputStream outputStream = Files.newOutputStream(zipPath)) {
            int len;
            while ((len = inputStream.read(buffer)) >= 0) {
                downloadedBytes += len;
                if (downloadedBytes > MAX_PACKAGE_BYTES) {
                    log.warn("SkillFactory远端ZIP包下载过大, packageUrl:{}, downloadedBytes:{}, maxBytes:{}",
                            uri, downloadedBytes, MAX_PACKAGE_BYTES);
                    throw new IllegalArgumentException(ERROR_PACKAGE_DOWNLOAD_TOO_LARGE);
                }
                outputStream.write(buffer, 0, len);
            }
        }
        if (downloadedBytes <= 0) {
            log.warn("SkillFactory远端ZIP包下载为空, packageUrl:{}", uri);
            throw new IllegalArgumentException(ERROR_PACKAGE_DOWNLOAD_EMPTY);
        }
        if (!StringUtils.endsWithIgnoreCase(uri.getPath(), ZIP_SUFFIX)) {
            log.info("SkillFactory远端packageUrl未以zip结尾，将继续按ZIP流校验, packageUrl:{}", uri);
        }
        log.info("SkillFactory远端ZIP包下载完成, packageUrl:{}, zipPath:{}, bytes:{}",
                uri, zipPath, downloadedBytes);
        return zipPath;
    }

    private int unzipToTemp(Path zipPath, Path tempDir, String... rootDirNames) throws IOException {
        Files.createDirectories(tempDir);
        int restoredFileCount = 0;
        try (ZipInputStream zipInputStream = new ZipInputStream(Files.newInputStream(zipPath))) {
            ZipEntry entry;
            while ((entry = zipInputStream.getNextEntry()) != null) {
                String relativePath = restoreRelativePath(entry.getName(), rootDirNames);
                if (StringUtils.isBlank(relativePath)) {
                    zipInputStream.closeEntry();
                    continue;
                }
                if (isIgnoredZipRelativePath(relativePath)) {
                    zipInputStream.closeEntry();
                    continue;
                }
                Path target = tempDir.resolve(relativePath).normalize();
                if (!target.startsWith(tempDir)) {
                    log.warn("SkillFactory本地包恢复失败，ZIP entry路径越界, zipPath:{}, entry:{}",
                            zipPath, entry.getName());
                    throw new IllegalArgumentException(ERROR_RESTORE_PATH_OUTSIDE_WORKSPACE);
                }
                if (entry.isDirectory()) {
                    Files.createDirectories(target);
                } else {
                    Files.createDirectories(target.getParent());
                    Files.copy(zipInputStream, target, StandardCopyOption.REPLACE_EXISTING);
                    restoredFileCount++;
                }
                zipInputStream.closeEntry();
            }
        }
        return restoredFileCount;
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
