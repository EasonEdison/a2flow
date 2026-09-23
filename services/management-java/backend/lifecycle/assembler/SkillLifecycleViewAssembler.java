package dev.a2flow.management.lifecycle.assembler;

import java.net.URI;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.lifecycle.domain.SkillWorkspaceFile;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.release.ReleaseModels.ReleaseDeployment;
import dev.a2flow.management.release.ReleaseModels.ReleaseVersion;

/**
 * Skill lifecycle 页面视图组装器。
 *
 * <p>该类把工作区文件和共享发布控制面的领域对象转换为 lifecycle 页面兼容字段，不查询数据库、
 * 不构建 ZIP，也不推进发布状态。正式版本只关联 ONLINE Deployment，避免误把同版本 PRT
 * 结果展示为线上记录。
 */
@Component
public class SkillLifecycleViewAssembler {

    private static final String EMPTY = "";
    private static final String PACKAGE_TYPE_PREPROD_SNAPSHOT = "PREPROD_SNAPSHOT";
    private static final String PACKAGE_TYPE_ONLINE_RELEASE = "ONLINE_RELEASE";
    private static final String PUBLISH_STAGE_PREPROD = "PREPROD_PUBLISH";
    private static final String PUBLISH_STAGE_ONLINE = "ONLINE_PUBLISH";
    private static final String STATUS_PACKAGE_BUILT_PLATFORM_PENDING = "PACKAGE_BUILT_PLATFORM_PENDING";
    private static final String FIELD_VERSION_ID = "versionId";
    private static final String FIELD_VERSION = "version";
    private static final String FIELD_VERSION_TYPE = "versionType";
    private static final String FIELD_PACKAGE_ID = "packageId";
    private static final String FIELD_PACKAGE_TYPE = "packageType";
    private static final String FIELD_ZIP_FILE_NAME = "zipFileName";
    private static final String FIELD_PACKAGE_URL = "packageUrl";
    private static final String FIELD_PACKAGE_DIGEST = "packageDigest";
    private static final String FIELD_FILE_TREE_DIGEST = "fileTreeDigest";
    private static final String FIELD_PACKAGE_STATUS = "packageStatus";
    private static final String FIELD_PUBLISH_STAGE = "publishStage";
    private static final String FIELD_PUBLISH_STATUS = "publishStatus";
    private static final String FIELD_EXTERNAL_PUBLISH_STAGE = "externalPublishStage";
    private static final String FIELD_AGENT_ENV = "agentEnv";
    private static final String FIELD_OBJECT_KEY = "objectKey";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_OPERATOR = "operator";
    private static final String FIELD_CREATE_TIME = "createTime";
    private static final String FIELD_UPDATE_TIME = "updateTime";
    private static final String FIELD_RETRYABLE = "retryable";
    private static final String FIELD_ERROR_CODE = "errorCode";
    private static final String FIELD_ARTIFACT = "artifact";
    private static final String FIELD_FILE_PATH = "filePath";
    private static final String FIELD_FILE_NAME = "fileName";
    private static final String FIELD_FILE_TYPE = "fileType";
    private static final String FIELD_FILE_SIZE = "fileSize";
    private static final String FIELD_CONTENT_DIGEST = "contentDigest";
    private static final String FIELD_MODIFY_TIME = "modifyTime";
    private static final String FIELD_CONTENT = "content";

    /**
     * 把文件系统扫描得到的领域对象转换为工作区页面文件视图。
     */
    public Map<String, Object> fileToMap(SkillWorkspaceFile file) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_FILE_PATH, file.getFilePath());
        result.put(FIELD_FILE_NAME, file.getFileName());
        result.put(FIELD_FILE_TYPE, file.getFileType());
        result.put(FIELD_FILE_SIZE, file.getFileSize());
        result.put(FIELD_CONTENT_DIGEST, file.getContentDigest());
        result.put(FIELD_MODIFY_TIME, file.getModifyTime());
        if (file.getContent() != null) {
            result.put(FIELD_CONTENT, file.getContent());
        }
        return result;
    }

    /**
     * 把共享发布产物与部署结果转换为页面发布记录。
     */
    public Map<String, Object> toMap(ReleaseArtifact artifact, Integer version, String packageType,
            ReleaseDeployment deployment) {
        Map<String, Object> result = new LinkedHashMap<>();
        String sourceId = deployment == null ? EMPTY : StringUtils.defaultString(deployment.getSourceId());
        result.put(FIELD_VERSION_ID, sourceId);
        result.put(FIELD_VERSION, defaultInteger(version));
        result.put(FIELD_VERSION_TYPE, packageType);
        result.put(FIELD_PACKAGE_ID, sourceId);
        result.put(FIELD_PACKAGE_TYPE, packageType);
        result.put(FIELD_ZIP_FILE_NAME, artifactFileName(artifact));
        result.put(FIELD_PACKAGE_URL, artifact == null ? EMPTY : artifact.getPackageUrl());
        result.put(FIELD_PACKAGE_DIGEST, artifact == null ? EMPTY : artifact.getPackageDigest());
        result.put(FIELD_FILE_TREE_DIGEST, artifact == null ? EMPTY : artifact.getFileTreeDigest());
        result.put(FIELD_PACKAGE_STATUS, deployment == null
                ? "PACKAGE_BUILT" : deployment.getStatus());
        result.put(FIELD_PUBLISH_STAGE, StringUtils.equals(packageType, PACKAGE_TYPE_PREPROD_SNAPSHOT)
                ? PUBLISH_STAGE_PREPROD : PUBLISH_STAGE_ONLINE);
        result.put(FIELD_PUBLISH_STATUS, deployment == null
                ? STATUS_PACKAGE_BUILT_PLATFORM_PENDING : deployment.getStatus());
        result.put(FIELD_EXTERNAL_PUBLISH_STAGE,
                deployment == null ? "PACKAGE_BUILT"
                        : deployment.getCurrentStage());
        result.put(FIELD_AGENT_ENV, deployment == null ? EMPTY : deployment.getEnvironment());
        result.put(FIELD_OBJECT_KEY, artifact == null ? EMPTY : artifact.getObjectKey());
        result.put(FIELD_MESSAGE, deployment == null ? EMPTY : deployment.getMessage());
        result.put(FIELD_OPERATOR, deployment == null ? EMPTY : deployment.getOperator());
        result.put(FIELD_CREATE_TIME, deployment == null ? 0L : defaultLong(deployment.getCreateTime()));
        result.put(FIELD_UPDATE_TIME, deployment == null ? 0L : defaultLong(deployment.getUpdateTime()));
        result.put(FIELD_RETRYABLE, deployment != null && Boolean.TRUE.equals(deployment.getRetryable()));
        result.put(FIELD_ERROR_CODE, deployment == null ? EMPTY : deployment.getErrorCode());
        result.put(FIELD_ARTIFACT, artifact);
        return result;
    }

    /**
     * 按正式版本倒序组装发布记录，只关联 ONLINE 环境部署。
     */
    public List<Map<String, Object>> releaseRecords(AssetReleaseState state) {
        return state.getVersions().stream()
                .sorted(Comparator.comparing(ReleaseVersion::getVersion,
                        Comparator.nullsLast(Comparator.reverseOrder())))
                .map(version -> toMap(version.getArtifact(), version.getVersion(),
                        PACKAGE_TYPE_ONLINE_RELEASE, latestOnlineDeployment(state, version.getVersion())))
                .collect(Collectors.toList());
    }

    private ReleaseDeployment latestOnlineDeployment(AssetReleaseState state, Integer sourceVersion) {
        return state.getDeployments().stream()
                .filter(item -> StringUtils.equals(item.getEnvironment(), ReleaseEnvironment.ONLINE.name()))
                .filter(item -> Objects.equals(item.getSourceVersion(), sourceVersion))
                .max(Comparator.comparing(item -> defaultLong(item.getUpdateTime())))
                .orElse(null);
    }

    private String artifactFileName(ReleaseArtifact artifact) {
        if (artifact == null || StringUtils.isBlank(artifact.getPackageUrl())) {
            return EMPTY;
        }
        try {
            Path path = Paths.get(URI.create(artifact.getPackageUrl()));
            return path.getFileName() == null ? EMPTY : path.getFileName().toString();
        } catch (RuntimeException e) {
            String packageUrl = artifact.getPackageUrl();
            int separator = packageUrl.lastIndexOf('/');
            return separator < 0 ? packageUrl : packageUrl.substring(separator + 1);
        }
    }

    private Integer defaultInteger(Integer value) {
        return value == null ? 0 : value;
    }

    private Long defaultLong(Long value) {
        return value == null ? 0L : value;
    }
}
