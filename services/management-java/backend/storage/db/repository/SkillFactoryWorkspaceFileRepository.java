package dev.a2flow.management.storage.db.repository;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Repository;

import dev.a2flow.management.fileguard.WorkspaceSnapshot;
import dev.a2flow.management.lifecycle.domain.SkillWorkspaceFile;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 工作区文件 Repository。
 *
 * <p>Path APIs operate on local staging directories only. The authoritative workspace document
 * is managed by {@link PostgresSkillWorkspaceStore}; callers must explicitly load/materialize and
 * persist with an expected revision. A directory on disk alone does not prove durable persistence.
 */
@Repository
@Slf4j
public class SkillFactoryWorkspaceFileRepository {

    public static final int MAX_TEXT_FILE_BYTES = 1024 * 1024;

    private static final String DIGEST_ALGORITHM = "SHA-256";
    private static final String DIGEST_PREFIX = "sha256:";
    private static final String HEX_FORMAT = "%02x";
    private static final String GIT_DIR_SEGMENT = "/.git/";
    private static final String PYTHON_CACHE_SEGMENT = "/__pycache__/";
    private static final String DS_STORE_SUFFIX = ".DS_Store";
    private static final String EXTENSION_MARKDOWN = ".md";
    private static final String EXTENSION_PYTHON = ".py";
    private static final String EXTENSION_JSON = ".json";
    private static final String FILE_TYPE_MARKDOWN = "MARKDOWN";
    private static final String FILE_TYPE_PYTHON = "PYTHON";
    private static final String FILE_TYPE_JSON = "JSON";
    private static final String FILE_TYPE_TEXT = "TEXT";
    private static final String ERROR_FILE_NOT_EXIST = "file does not exist";
    private static final String ERROR_FILE_TOO_LARGE = "file is too large";
    private static final String ERROR_DIGEST_NOT_SUPPORTED = "SHA-256 not supported";

    /** Capture an explicitly edited staging directory, preserving existing entry handles. */
    public PostgresSkillWorkspaceStore.Document captureDocument(PostgresSkillWorkspaceStore store,
            PostgresSkillWorkspaceStore.Document previous, Path workspace) throws IOException {
        PostgresSkillWorkspaceStore.validate(previous);
        PostgresSkillWorkspaceStore.Document document = new PostgresSkillWorkspaceStore.Document();
        document.baseDraftRevision = previous.baseDraftRevision;
        Map<String, String> handles = new LinkedHashMap<>();
        Map<String, String> mediaTypes = new LinkedHashMap<>();
        for (PostgresSkillWorkspaceStore.Entry entry : previous.entries) {
            handles.put(entry.logicalPath, entry.handleId);
            mediaTypes.put(entry.logicalPath, entry.mediaType);
        }
        Path root = workspace.toRealPath();
        for (Path path : listFiles(root)) {
            if (Files.isSymbolicLink(path) || !path.toRealPath().startsWith(root)
                    || !Files.isRegularFile(path, java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
                throw new IOException("Workspace contains a nonregular or escaping file");
            }
            String logicalPath = normalize(root.relativize(path));
            String mediaType = mediaTypes.containsKey(logicalPath)
                    ? mediaTypes.get(logicalPath) : Files.probeContentType(path);
            document = store.put(document, logicalPath,
                    mediaType == null ? "application/octet-stream" : mediaType, Files.readAllBytes(path));
        }
        for (PostgresSkillWorkspaceStore.Entry entry : document.entries) {
            if (handles.containsKey(entry.logicalPath)) {
                entry.handleId = handles.get(entry.logicalPath);
            }
        }
        document.dirty = true;
        PostgresSkillWorkspaceStore.validate(document);
        return document;
    }
    /**
     * 如果文件不存在，则写入初始化内容；已存在时不覆盖用户文件。
     */
    public void writeIfAbsent(Path file, String content) throws IOException {
        if (!Files.exists(file)) {
            Files.createDirectories(file.getParent());
            Files.write(file, content.getBytes(StandardCharsets.UTF_8), StandardOpenOption.CREATE_NEW);
            log.info("SkillFactory初始化工作区文件, filePath:{}", file);
        }
    }

    /**
     * 读取文本文件内容，并限制文件大小，避免把大文件作为页面文本返回。
     */
    public String readText(Path file) throws IOException {
        ensureTextFile(file);
        return new String(Files.readAllBytes(file), StandardCharsets.UTF_8);
    }

    /**
     * 覆盖写入文本文件内容。
     */
    public void writeText(Path file, String content) throws IOException {
        Files.createDirectories(file.getParent());
        Files.write(file, StringUtils.defaultString(content).getBytes(StandardCharsets.UTF_8),
                StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
        log.info("SkillFactory写入工作区文件, filePath:{}, contentLength:{}",
                file, StringUtils.defaultString(content).length());
    }

    /**
     * 扫描 workspace 内可参与 Skill 包构建和摘要计算的文件。
     */
    public List<Path> listFiles(Path workspace) throws IOException {
        List<Path> files = new ArrayList<>();
        if (!Files.exists(workspace)) {
            return files;
        }
        Files.walkFileTree(workspace, new SimpleFileVisitor<Path>() {
            @Override
            public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                if (!isIgnored(file)) {
                    files.add(file);
                }
                return FileVisitResult.CONTINUE;
            }
        });
        log.info("SkillFactory扫描工作区文件完成, workspacePath:{}, fileCount:{}", workspace, files.size());
        return files;
    }

    /**
     * 将 workspace 本地文件扫描结果转换成文件领域对象列表。
     */
    public List<SkillWorkspaceFile> files(Path workspace) throws IOException {
        return listFiles(workspace).stream()
                .map(path -> file(workspace, path))
                .collect(Collectors.toList());
    }

    /**
     * 基于单个本地文件组装文件领域对象。
     */
    public SkillWorkspaceFile file(Path workspace, Path file) {
        try {
            return new SkillWorkspaceFile()
                    .setFilePath(normalize(workspace.relativize(file)))
                    .setFileName(file.getFileName().toString())
                    .setFileType(fileType(file))
                    .setFileSize(Files.size(file))
                    .setContentDigest(sha256(Files.readAllBytes(file)))
                    .setModifyTime(Files.getLastModifiedTime(file).toMillis());
        } catch (IOException e) {
            log.warn("SkillFactory组装文件元数据失败, workspacePath:{}, filePath:{}", workspace, file, e);
            throw new IllegalStateException(e);
        }
    }

    /**
     * 列出当前目录下一级子节点，目录排在文件前面。
     */
    public List<Path> listChildren(Path path) throws IOException {
        List<Path> children = new ArrayList<>();
        try (java.util.stream.Stream<Path> stream = Files.list(path)) {
            stream.forEach(children::add);
        }
        children.sort(Comparator.comparing((Path child) -> Files.isRegularFile(child))
                .thenComparing(Path::toString));
        return children;
    }

    public boolean isDirectory(Path path) {
        return Files.isDirectory(path);
    }

    public boolean exists(Path path) {
        return Files.exists(path);
    }

    public long size(Path path) throws IOException {
        return Files.size(path);
    }

    /**
     * 一次扫描生成 canonical workspace 快照。
     *
     * <p>文件树摘要固定按规范化相对路径排序，并对路径和原始文件字节分别添加长度边界后计算；
     * 逐文件摘要按原始文件字节计算。生命周期、AI Coding、验证和发布链路必须复用这一结果，
     * 避免同一工作区出现多种摘要。
     */
    public WorkspaceSnapshot captureWorkspaceSnapshot(Path workspace) throws IOException {
        MessageDigest treeDigest = newDigest();
        List<Path> files = listFiles(workspace);
        files.sort(Comparator.comparing(file -> normalize(workspace.relativize(file))));
        Map<String, String> fileDigestMap = new LinkedHashMap<>();
        for (Path file : files) {
            String relativePath = normalize(workspace.relativize(file));
            byte[] pathBytes = relativePath.getBytes(StandardCharsets.UTF_8);
            byte[] fileBytes = Files.readAllBytes(file);
            treeDigest.update(ByteBuffer.allocate(Integer.BYTES).putInt(pathBytes.length).array());
            treeDigest.update(pathBytes);
            treeDigest.update(ByteBuffer.allocate(Long.BYTES).putLong(fileBytes.length).array());
            treeDigest.update(fileBytes);
            fileDigestMap.put(relativePath, sha256(fileBytes));
        }
        WorkspaceSnapshot snapshot = new WorkspaceSnapshot();
        snapshot.setRootPath(workspace.toAbsolutePath().normalize().toString());
        snapshot.setFileTreeDigest(DIGEST_PREFIX + bytesToHex(treeDigest.digest()));
        snapshot.setFileDigestMap(fileDigestMap);
        snapshot.setFileCount(fileDigestMap.size());
        snapshot.setSnapshotTime(System.currentTimeMillis());
        log.info("SkillFactory采集canonical工作区快照完成, workspacePath:{}, fileTreeDigest:{}, fileCount:{}",
                workspace, snapshot.getFileTreeDigest(), snapshot.getFileCount());
        return snapshot;
    }

    /**
     * 返回 canonical workspace 文件树摘要。
     */
    public String digestWorkspace(Path workspace) throws IOException {
        return captureWorkspaceSnapshot(workspace).getFileTreeDigest();
    }

    public String sha256(byte[] bytes) {
        MessageDigest digest = newDigest();
        digest.update(bytes);
        return DIGEST_PREFIX + bytesToHex(digest.digest());
    }

    private void ensureTextFile(Path file) throws IOException {
        if (!Files.exists(file) || Files.isDirectory(file)) {
            log.warn("SkillFactory读取文本文件失败，文件不存在或是目录, filePath:{}", file);
            throw new IllegalArgumentException(ERROR_FILE_NOT_EXIST);
        }
        if (Files.size(file) > MAX_TEXT_FILE_BYTES) {
            log.warn("SkillFactory读取文本文件失败，文件过大, filePath:{}, fileSize:{}",
                    file, Files.size(file));
            throw new IllegalArgumentException(ERROR_FILE_TOO_LARGE);
        }
    }

    private String fileType(Path file) {
        String name = file.getFileName().toString();
        if (StringUtils.endsWith(name, EXTENSION_MARKDOWN)) {
            return FILE_TYPE_MARKDOWN;
        }
        if (StringUtils.endsWith(name, EXTENSION_PYTHON)) {
            return FILE_TYPE_PYTHON;
        }
        if (StringUtils.endsWith(name, EXTENSION_JSON)) {
            return FILE_TYPE_JSON;
        }
        return FILE_TYPE_TEXT;
    }

    private MessageDigest newDigest() {
        try {
            return MessageDigest.getInstance(DIGEST_ALGORITHM);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(ERROR_DIGEST_NOT_SUPPORTED, e);
        }
    }

    private String bytesToHex(byte[] bytes) {
        StringBuilder builder = new StringBuilder();
        for (byte b : bytes) {
            builder.append(String.format(HEX_FORMAT, b));
        }
        return builder.toString();
    }

    private boolean isIgnored(Path file) {
        String path = normalize(file);
        return path.contains(GIT_DIR_SEGMENT)
                || path.contains(PYTHON_CACHE_SEGMENT)
                || path.endsWith(DS_STORE_SUFFIX);
    }

    private String normalize(Path path) {
        return path.normalize().toString().replace('\\', '/');
    }
}
