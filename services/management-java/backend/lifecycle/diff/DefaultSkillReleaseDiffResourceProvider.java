package dev.a2flow.management.lifecycle.diff;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.lifecycle.domain.SkillWorkspaceFile;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.diff.ReleaseDiffContentType;
import dev.a2flow.management.release.diff.ReleaseDiffResource;
import dev.a2flow.management.release.diff.SkillReleaseDiffResourceProvider;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceFileRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * Skill 正式发布 Diff 的受控文件资源提供器。
 *
 * <p>本类位于 lifecycle 边界，负责把当前 `preprod/current` 或指定
 * `online/releases/{version}` 下的真实文件转换成共享发布 Diff 资源。上游
 * `SkillReleaseAssetAdapter` 只通过 {@link SkillReleaseDiffResourceProvider} 获取文件，
 * 下游共享 {@code ReleaseDiffEngine} 负责行级比较、JSON 规范化和 hunk 生成。
 *
 * <p>本类不计算 Diff、不读取其他 workspace、不恢复版本，也不修改任何文件。所有路径都必须由
 * {@link SkillFactoryWorkspaceRepository} 派生，符号链接、越界路径和不存在的版本目录会明确失败。
 */
@Service
@Slf4j
public class DefaultSkillReleaseDiffResourceProvider implements SkillReleaseDiffResourceProvider {

    private static final String DIR_PREPROD = "preprod";
    private static final String DIR_CURRENT = "current";
    private static final String DIR_ONLINE = "online";
    private static final String DIR_RELEASES = "releases";
    private static final String PATH_SEPARATOR = "/";
    private static final String JSON_EXTENSION = ".json";
    private static final String DEFAULT_TEXT_LANGUAGE = "text";
    private static final String JSON_LANGUAGE = "json";
    private static final String SOURCE_CURRENT = "CURRENT";
    private static final String ERROR_CURRENT_WORKSPACE_NOT_FOUND = "Skill当前编辑工作区不存在";
    private static final String ERROR_RELEASE_VERSION_INVALID = "Skill正式版本必须是正整数";
    private static final String ERROR_RELEASE_WORKSPACE_NOT_FOUND = "Skill正式版本目录不存在";
    private static final String ERROR_TARGET_SNAPSHOT_MISMATCH = "Skill正式版本快照与当前Skill不匹配";
    private static final String ERROR_RESOURCE_PATH_UNSAFE = "Skill发布Diff文件路径越界";
    private static final String ERROR_SYMBOLIC_LINK_UNSUPPORTED = "Skill发布Diff不允许符号链接";
    private static final String ERROR_RESOURCE_READ_FAILED = "Skill发布Diff文件资源读取失败";

    private static final Set<String> BINARY_EXTENSIONS = Set.of(
            ".7z", ".avi", ".bin", ".bmp", ".class", ".doc", ".docx", ".eot", ".exe", ".gif",
            ".gz", ".ico", ".jar", ".jpeg", ".jpg", ".mov", ".mp3", ".mp4", ".otf", ".pdf",
            ".png", ".ppt", ".pptx", ".rar", ".so", ".tar", ".ttf", ".wav", ".webp", ".woff",
            ".woff2", ".xls", ".xlsx", ".zip");

    private static final Map<String, String> TEXT_LANGUAGE_BY_EXTENSION = Map.ofEntries(
            Map.entry(".c", "c"),
            Map.entry(".conf", "text"),
            Map.entry(".cpp", "cpp"),
            Map.entry(".css", "css"),
            Map.entry(".go", "go"),
            Map.entry(".gradle", "groovy"),
            Map.entry(".h", "c"),
            Map.entry(".html", "html"),
            Map.entry(".ini", "text"),
            Map.entry(".java", "java"),
            Map.entry(".js", "javascript"),
            Map.entry(".json", JSON_LANGUAGE),
            Map.entry(".jsx", "javascript"),
            Map.entry(".kt", "kotlin"),
            Map.entry(".kts", "kotlin"),
            Map.entry(".less", "less"),
            Map.entry(".md", "markdown"),
            Map.entry(".php", "php"),
            Map.entry(".properties", "properties"),
            Map.entry(".proto", "protobuf"),
            Map.entry(".py", "python"),
            Map.entry(".rb", "ruby"),
            Map.entry(".rs", "rust"),
            Map.entry(".scss", "scss"),
            Map.entry(".sh", "shell"),
            Map.entry(".sql", "sql"),
            Map.entry(".text", DEFAULT_TEXT_LANGUAGE),
            Map.entry(".toml", "toml"),
            Map.entry(".ts", "typescript"),
            Map.entry(".tsx", "typescript"),
            Map.entry(".txt", DEFAULT_TEXT_LANGUAGE),
            Map.entry(".vue", "vue"),
            Map.entry(".xml", "xml"),
            Map.entry(".yaml", "yaml"),
            Map.entry(".yml", "yaml"));

    @Resource
    private SkillFactoryWorkspaceRepository workspaceRepository;

    @Resource
    private SkillFactoryWorkspaceFileRepository fileRepository;

    /**
     * 读取当前 Skill 的 `preprod/current` 文件资源。
     *
     * @param skillCode Skill 稳定英文标识，同时也是 workspaceId
     * @param params 共享发布调用参数，本实现不信任其中的目录或版本覆盖值
     * @return 按相对路径排序的受控文件资源
     */
    @Override
    public List<ReleaseDiffResource> currentResources(String skillCode, Map<String, String> params) {
        Path root = workspaceRepository.resolveWorkspace(skillCode)
                .resolve(DIR_PREPROD)
                .resolve(DIR_CURRENT)
                .normalize();
        requireDirectory(root, ERROR_CURRENT_WORKSPACE_NOT_FOUND);
        log.info("Skill发布Diff开始读取当前工作区资源, skillCode:{}, workspacePath:{}",
                skillCode, root);
        return resources(skillCode, root, SOURCE_CURRENT);
    }

    /**
     * 读取指定正式数字版本的 `online/releases/{version}` 文件资源。
     *
     * @param skillCode Skill 稳定英文标识，同时也是 workspaceId
     * @param version 共享发布控制面选中的正式数字版本
     * @param targetSnapshot 该正式版本冻结的 Skill 快照，只用于校验资产身份
     * @param params 共享发布调用参数，本实现不信任其中的目录或版本覆盖值
     * @return 按相对路径排序的受控文件资源
     */
    @Override
    public List<ReleaseDiffResource> versionResources(String skillCode, Integer version,
            AssetSnapshot targetSnapshot, Map<String, String> params) {
        if (version == null || version <= 0) {
            log.warn("Skill发布Diff正式版本非法, skillCode:{}, version:{}", skillCode, version);
            throw new IllegalArgumentException(ERROR_RELEASE_VERSION_INVALID);
        }
        if (targetSnapshot == null || !StringUtils.equals(skillCode, targetSnapshot.getAssetKey())) {
            log.warn("Skill发布Diff正式版本快照身份不一致, skillCode:{}, version:{}, targetAssetKey:{}",
                    skillCode, version, targetSnapshot == null ? null : targetSnapshot.getAssetKey());
            throw new IllegalArgumentException(ERROR_TARGET_SNAPSHOT_MISMATCH);
        }
        Path root = workspaceRepository.resolveWorkspace(skillCode)
                .resolve(DIR_ONLINE)
                .resolve(DIR_RELEASES)
                .resolve(String.valueOf(version))
                .normalize();
        requireDirectory(root, ERROR_RELEASE_WORKSPACE_NOT_FOUND);
        log.info("Skill发布Diff开始读取正式版本资源, skillCode:{}, version:{}, releasePath:{}",
                skillCode, version, root);
        return resources(skillCode, root, String.valueOf(version));
    }

    private List<ReleaseDiffResource> resources(String skillCode, Path root, String sourceLabel) {
        try {
            List<ReleaseDiffResource> resources = fileRepository.listFiles(root).stream()
                    .map(file -> resource(root, file))
                    .sorted((left, right) -> left.getPath().compareTo(right.getPath()))
                    .collect(Collectors.toList());
            log.info("Skill发布Diff文件资源读取完成, skillCode:{}, source:{}, fileCount:{}",
                    skillCode, sourceLabel, resources.size());
            return resources;
        } catch (IOException e) {
            log.warn("Skill发布Diff文件资源读取失败, skillCode:{}, source:{}, root:{}",
                    skillCode, sourceLabel, root, e);
            throw new IllegalStateException(ERROR_RESOURCE_READ_FAILED, e);
        }
    }

    private ReleaseDiffResource resource(Path root, Path file) {
        Path normalizedRoot = root.normalize();
        Path normalizedFile = file.normalize();
        if (!normalizedFile.startsWith(normalizedRoot)) {
            log.warn("Skill发布Diff文件路径越界, root:{}, file:{}", normalizedRoot, normalizedFile);
            throw new IllegalArgumentException(ERROR_RESOURCE_PATH_UNSAFE);
        }
        if (Files.isSymbolicLink(normalizedFile)) {
            log.warn("Skill发布Diff拒绝符号链接, root:{}, file:{}", normalizedRoot, normalizedFile);
            throw new IllegalArgumentException(ERROR_SYMBOLIC_LINK_UNSUPPORTED);
        }
        String path = normalize(normalizedRoot.relativize(normalizedFile));
        String extension = extension(path);
        SkillWorkspaceFile metadata = fileRepository.file(normalizedRoot, normalizedFile);
        ReleaseDiffContentType contentType = contentType(extension);
        String content = contentType == ReleaseDiffContentType.BINARY
                ? null : readText(normalizedFile, path);
        return new ReleaseDiffResource()
                .setPath(path)
                .setContentType(contentType)
                .setLanguage(language(extension, contentType))
                .setDigest(metadata.getContentDigest())
                .setSize(metadata.getFileSize())
                .setContent(content);
    }

    private String readText(Path file, String relativePath) {
        try {
            return fileRepository.readText(file);
        } catch (IOException | IllegalArgumentException e) {
            log.warn("Skill发布Diff文本文件读取失败, filePath:{}, relativePath:{}",
                    file, relativePath, e);
            throw new IllegalStateException(ERROR_RESOURCE_READ_FAILED + ": " + relativePath, e);
        }
    }

    private ReleaseDiffContentType contentType(String extension) {
        if (StringUtils.equals(extension, JSON_EXTENSION)) {
            return ReleaseDiffContentType.JSON;
        }
        return BINARY_EXTENSIONS.contains(extension)
                ? ReleaseDiffContentType.BINARY : ReleaseDiffContentType.TEXT;
    }

    private String language(String extension, ReleaseDiffContentType contentType) {
        if (contentType == ReleaseDiffContentType.JSON) {
            return JSON_LANGUAGE;
        }
        if (contentType == ReleaseDiffContentType.BINARY) {
            return DEFAULT_TEXT_LANGUAGE;
        }
        return TEXT_LANGUAGE_BY_EXTENSION.getOrDefault(extension, DEFAULT_TEXT_LANGUAGE);
    }

    private String extension(String path) {
        int separatorIndex = path.lastIndexOf(PATH_SEPARATOR);
        String fileName = separatorIndex < 0 ? path : path.substring(separatorIndex + 1);
        int dotIndex = fileName.lastIndexOf('.');
        return dotIndex < 0 ? StringUtils.EMPTY
                : fileName.substring(dotIndex).toLowerCase(Locale.ROOT);
    }

    private void requireDirectory(Path directory, String errorMessage) {
        if (!Files.isDirectory(directory)) {
            log.warn("Skill发布Diff目录不存在, directory:{}, errorMessage:{}", directory, errorMessage);
            throw new IllegalArgumentException(errorMessage);
        }
    }

    private String normalize(Path path) {
        return path.normalize().toString().replace('\\', '/');
    }
}
