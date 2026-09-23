package dev.a2flow.management.lifecycle;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.lifecycle.artifact.SkillPackageArtifactService;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.lifecycle.artifact.DatabaseArtifactService;
import dev.a2flow.management.model.SkillFactoryEntityRelationConstants;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.release.ReleaseModels.ReleaseBuild;
import dev.a2flow.management.release.ReleaseModels.ReleaseDeployment;
import dev.a2flow.management.release.ReleaseModels.ReleaseRelationEntry;
import dev.a2flow.management.release.ReleaseModels.ReleaseRelationSnapshot;
import dev.a2flow.management.storage.db.entity.EntityRelationDO;
import dev.a2flow.management.storage.db.repository.EntityRelationRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceFileRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceRepository;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;

/**
 * Skill 成功 PRT Build 的恢复事实服务。
 *
 * <p>上游发布 Adapter 在 Build 创建时调用本服务冻结当前 Skill 数字版本的全部通用实体关系；工作区
 * Service 在重置时调用本服务筛选成功 Build，从数据库读取并校验不可变包，再恢复文件和关系。
 * 本服务不修改草稿写保护投影、ACTIVE Change、正式 Version 或环境指针，也不把旧 Build 的来源版本
 * 写回当前 Skill。
 */
@Service
@Slf4j
public class SkillPreprodBuildRestoreService {

    private static final String STATUS_SUCCEEDED = "SUCCEEDED";
    private static final String ENVIRONMENT_PREPROD = "PRT";
    private static final String SOURCE_TYPE_BUILD = "BUILD";
    private static final String FIELD_SOURCE_TYPE = "sourceType";
    private static final String FIELD_SOURCE_ID = "sourceId";
    private static final String FIELD_BUILD_NUMBER = "buildNumber";
    private static final String FIELD_TARGET_VERSION = "targetVersion";
    private static final String FIELD_CREATE_TIME = "createTime";
    private static final String FIELD_COMPLETION_TIME = "completionTime";
    private static final String FIELD_OPERATOR = "operator";
    private static final String FIELD_PACKAGE_DIGEST = "packageDigest";
    private static final String FIELD_LABEL = "label";
    private static final String BUILD_LABEL_PREFIX = "PRT Build #";
    private static final String BUILD_LABEL_VERSION_SEPARATOR = " · 目标版本 ";
    private static final String ERROR_SKILL_DRAFT_INVALID = "Skill Build关系快照缺少有效草稿身份";
    private static final String ERROR_BUILD_NOT_RESTORABLE = "指定PRT Build不可恢复";
    private static final String ERROR_RELATION_SNAPSHOT_INCOMPLETE = "PRT Build关系快照不完整";
    private static final String ERROR_PACKAGE_DIGEST_MISMATCH = "PRT Build ZIP摘要校验失败";
    private static final String ERROR_RELEASE_VERSION_NOT_FOUND = "正式版本目录不存在";
    private static final String ERROR_RELEASE_VERSION_RECORD_NOT_FOUND = "正式版本记录不存在或产物不完整";

    @Resource
    private SkillFactoryWorkspaceRepository workspaceRepository;

    @Resource
    private EntityRelationRepository entityRelationRepository;

    @Resource
    private DatabaseArtifactService databaseArtifacts;

    @Resource
    private SkillPackageArtifactService packageArtifactService;

    @Resource
    private SkillFactoryWorkspaceFileRepository fileRepository;

    /** 在 Build 创建时冻结当前 Skill 数字版本的全部通用实体关系。 */
    public ReleaseRelationSnapshot freezeCurrentRelations(String skillCode) {
        SkillDraft draft = workspaceRepository.findDraftBySkillCode(skillCode);
        requireDraftIdentity(draft);
        List<EntityRelationDO> relations = entityRelationRepository.listBySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_SKILL,
                String.valueOf(draft.getId()), draft.getVersion());
        List<ReleaseRelationEntry> entries = new ArrayList<>(relations.size());
        relations.stream()
                .sorted(Comparator.comparing(item -> item.getSortNo() == null ? 0 : item.getSortNo()))
                .map(this::toSnapshotEntry)
                .forEach(entries::add);
        log.info("Skill PRT Build关系快照冻结完成, skillCode:{}, skillVersion:{}, relationCount:{}",
                skillCode, draft.getVersion(), entries.size());
        return new ReleaseRelationSnapshot()
                .setContractVersion(ReleaseRelationSnapshot.CURRENT_CONTRACT_VERSION)
                .setComplete(true)
                .setRelations(entries);
    }

    /** 只投影拥有完整成功发布事实的 PRT Build，旧 Build 和失败流水保持审计可见但不可选择。 */
    public List<Map<String, Object>> selectableBuildSources(AssetReleaseState state) {
        if (state == null || state.getBuilds() == null) {
            return List.of();
        }
        List<Map<String, Object>> sources = new ArrayList<>();
        state.getBuilds().stream()
                .filter(build -> isRestorable(state, build))
                .sorted(Comparator.comparing(
                        (ReleaseBuild build) -> build.getCreateTime() == null ? 0L : build.getCreateTime())
                        .reversed())
                .flatMap(build -> succeededDeployment(state, build).stream()
                        .map(deployment -> sourceView(build, deployment)))
                .forEach(sources::add);
        return sources;
    }

    /**
     * 按成功 Build 的不可变 Artifact 恢复工作区和完整关系。
     *
     * <p>所有 Build/Deployment/Artifact/关系快照和 ZIP 摘要校验都在文件替换前完成；不允许回退到
     * 本地可覆盖的 snapshot.zip，也不允许对旧不完整 Build 做文件单独恢复。
     */
    public BuildRestoreResult restoreBuild(String workspaceId, SkillDraft currentDraft,
            AssetReleaseState state, String buildId, Path workspaceRoot, Path editableWorkspace,
            String operator) throws IOException {
        requireDraftIdentity(currentDraft);
        ReleaseBuild build = requireRestorableBuild(state, buildId);
        ReleaseArtifact artifact = build.getArtifact();
        log.warn("SkillFactory开始从PRT Build重置当前变更, workspaceId:{}, buildId:{}, "
                        + "targetVersion:{}, objectKey:{}",
                workspaceId, buildId, currentDraft.getVersion(), artifact.getObjectKey());
        byte[] zipBytes = databaseArtifacts.load(workspaceId, artifact);
        String actualDigest = fileRepository.sha256(zipBytes);
        if (!StringUtils.equals(actualDigest, artifact.getPackageDigest())) {
            log.warn("SkillFactory拒绝恢复摘要不一致的PRT Build ZIP, workspaceId:{}, buildId:{}, "
                            + "expectedDigest:{}, actualDigest:{}",
                    workspaceId, buildId, artifact.getPackageDigest(), actualDigest);
            throw new IllegalArgumentException(ERROR_PACKAGE_DIGEST_MISMATCH);
        }
        int restoredFileCount = packageArtifactService.restoreImmutablePackage(
                workspaceRoot, editableWorkspace, zipBytes, workspaceId);
        int restoredRelationCount = restoreRelations(currentDraft, build.getRelationSnapshot(), operator);
        log.warn("SkillFactory从PRT Build重置当前变更完成, workspaceId:{}, buildId:{}, "
                        + "targetVersion:{}, restoredFileCount:{}, restoredRelationCount:{}",
                workspaceId, buildId, currentDraft.getVersion(), restoredFileCount, restoredRelationCount);
        return new BuildRestoreResult(build, restoredFileCount, restoredRelationCount);
    }

    /** 从共享 ReleaseVersion 对应的数据库不可变包恢复文件和关系，不依赖旧磁盘目录。 */
    public int restoreVersion(SkillDraft currentDraft, AssetReleaseState state,
            int sourceVersion, int targetVersion, Path releaseWorkspace, Path editableWorkspace, String operator)
            throws IOException {
        requireDraftIdentity(currentDraft);
        if (state == null || state.getVersions() == null) {
            throw new IllegalArgumentException(ERROR_RELEASE_VERSION_RECORD_NOT_FOUND);
        }
        ReleaseArtifact artifact = state.getVersions().stream()
                .filter(version -> version.getVersion() != null && version.getVersion() == sourceVersion)
                .map(version -> version.getArtifact())
                .filter(this::validVersionArtifact)
                .findFirst().orElseThrow(() -> new IllegalArgumentException(ERROR_RELEASE_VERSION_RECORD_NOT_FOUND));
        byte[] zipBytes = databaseArtifacts.load(currentDraft.getWorkspaceId(), artifact);
        packageArtifactService.restoreImmutablePackage(workspaceRepository.workspaceRoot(),
                editableWorkspace, zipBytes, currentDraft.getWorkspaceId());
        List<EntityRelationDO> restored = entityRelationRepository.copySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_SKILL,
                String.valueOf(currentDraft.getId()), sourceVersion, targetVersion, operator);
        log.warn("SkillFactory从正式版本恢复当前变更完成, workspaceId:{}, sourceVersion:{}, "
                        + "targetVersion:{}, relationCount:{}",
                currentDraft.getWorkspaceId(), sourceVersion, targetVersion, restored.size());
        return restored.size();
    }

    /** 把冻结关系完整覆盖到当前 Skill 数字版本。 */
    public int restoreRelations(SkillDraft currentDraft, ReleaseRelationSnapshot snapshot, String operator) {
        requireDraftIdentity(currentDraft);
        requireCompleteSnapshot(snapshot);
        List<EntityRelationDO> relations = new ArrayList<>(snapshot.getRelations().size());
        for (ReleaseRelationEntry entry : snapshot.getRelations()) {
            relations.add(toRelation(currentDraft, entry));
        }
        List<EntityRelationDO> restored = entityRelationRepository.replaceBySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_SKILL,
                String.valueOf(currentDraft.getId()), currentDraft.getVersion(), relations, operator);
        return restored.size();
    }

    private ReleaseBuild requireRestorableBuild(AssetReleaseState state, String buildId) {
        if (state == null || state.getBuilds() == null || StringUtils.isBlank(buildId)) {
            throw new IllegalArgumentException(ERROR_BUILD_NOT_RESTORABLE);
        }
        return state.getBuilds().stream()
                .filter(build -> StringUtils.equals(buildId, build.getBuildId()))
                .filter(build -> isRestorable(state, build))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(ERROR_BUILD_NOT_RESTORABLE));
    }

    private boolean isRestorable(AssetReleaseState state, ReleaseBuild build) {
        if (build == null || !StringUtils.equals(STATUS_SUCCEEDED, build.getStatus())
                || !completeSnapshot(build.getRelationSnapshot()) || !validBuildArtifact(build.getArtifact())) {
            return false;
        }
        return succeededDeployment(state, build).isPresent();
    }

    private Optional<ReleaseDeployment> succeededDeployment(AssetReleaseState state, ReleaseBuild build) {
        if (state.getDeployments() == null) {
            return Optional.empty();
        }
        return state.getDeployments().stream()
                .filter(deployment -> matchingSucceededDeployment(build, deployment))
                .max(Comparator.comparing(deployment -> deployment.getUpdateTime() == null
                        ? defaultLong(deployment.getCreateTime()) : deployment.getUpdateTime()));
    }

    private boolean matchingSucceededDeployment(ReleaseBuild build, ReleaseDeployment deployment) {
        return deployment != null
                && StringUtils.equals(ENVIRONMENT_PREPROD, deployment.getEnvironment())
                && StringUtils.equals(SOURCE_TYPE_BUILD, deployment.getSourceType())
                && StringUtils.equals(build.getBuildId(), deployment.getSourceId())
                && StringUtils.equals(STATUS_SUCCEEDED, deployment.getStatus());
    }

    private boolean validBuildArtifact(ReleaseArtifact artifact) {
        return validVersionArtifact(artifact);
    }

    private boolean validVersionArtifact(ReleaseArtifact artifact) {
        return artifact != null && "POSTGRESQL".equals(artifact.getStorageProvider())
                && StringUtils.isNotBlank(artifact.getPackageDigest())
                && artifact.getPackageDigest().equals(artifact.getObjectKey());
    }

    private String firstNonBlank(String first, String second) {
        return StringUtils.isNotBlank(first) ? first : second;
    }

    private boolean completeSnapshot(ReleaseRelationSnapshot snapshot) {
        return snapshot != null
                && Integer.valueOf(ReleaseRelationSnapshot.CURRENT_CONTRACT_VERSION)
                        .equals(snapshot.getContractVersion())
                && Boolean.TRUE.equals(snapshot.getComplete())
                && snapshot.getRelations() != null;
    }

    private void requireCompleteSnapshot(ReleaseRelationSnapshot snapshot) {
        if (!completeSnapshot(snapshot)) {
            throw new IllegalArgumentException(ERROR_RELATION_SNAPSHOT_INCOMPLETE);
        }
    }

    private void requireDraftIdentity(SkillDraft draft) {
        if (draft == null || draft.getId() == null || draft.getVersion() == null || draft.getVersion() <= 0) {
            throw new IllegalArgumentException(ERROR_SKILL_DRAFT_INVALID);
        }
    }

    private Map<String, Object> sourceView(ReleaseBuild build, ReleaseDeployment deployment) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_SOURCE_TYPE, SOURCE_TYPE_BUILD);
        result.put(FIELD_SOURCE_ID, build.getBuildId());
        result.put(FIELD_BUILD_NUMBER, build.getBuildNumber());
        result.put(FIELD_TARGET_VERSION, build.getTargetVersion());
        result.put(FIELD_CREATE_TIME, build.getCreateTime());
        result.put(FIELD_COMPLETION_TIME, deployment.getUpdateTime() == null
                ? deployment.getCreateTime() : deployment.getUpdateTime());
        result.put(FIELD_OPERATOR, StringUtils.defaultIfBlank(build.getOperator(), deployment.getOperator()));
        result.put(FIELD_PACKAGE_DIGEST, build.getArtifact().getPackageDigest());
        result.put(FIELD_LABEL, BUILD_LABEL_PREFIX + build.getBuildNumber()
                + BUILD_LABEL_VERSION_SEPARATOR + build.getTargetVersion());
        return result;
    }

    private long defaultLong(Long value) {
        return value == null ? 0L : value;
    }

    private ReleaseRelationEntry toSnapshotEntry(EntityRelationDO relation) {
        return new ReleaseRelationEntry()
                .setRelationType(relation.getRelationType())
                .setTargetEntityType(relation.getTargetEntityType())
                .setTargetEntityId(relation.getTargetEntityId())
                .setTargetEntityCode(relation.getTargetEntityCode())
                .setTargetVersion(relation.getTargetVersion())
                .setRelationMode(relation.getRelationMode())
                .setSnapshotJson(relation.getSnapshotJson())
                .setSortNo(relation.getSortNo())
                .setAttribute(relation.getAttribute());
    }

    private EntityRelationDO toRelation(SkillDraft currentDraft, ReleaseRelationEntry entry) {
        if (entry == null) {
            throw new IllegalArgumentException(ERROR_RELATION_SNAPSHOT_INCOMPLETE);
        }
        return new EntityRelationDO()
                .setNamespace(SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY)
                .setSourceEntityType(SkillFactoryEntityRelationConstants.ENTITY_TYPE_SKILL)
                .setSourceEntityId(String.valueOf(currentDraft.getId()))
                .setSourceVersion(currentDraft.getVersion())
                .setRelationType(entry.getRelationType())
                .setTargetEntityType(entry.getTargetEntityType())
                .setTargetEntityId(entry.getTargetEntityId())
                .setTargetEntityCode(entry.getTargetEntityCode())
                .setTargetVersion(entry.getTargetVersion())
                .setRelationMode(entry.getRelationMode())
                .setSnapshotJson(entry.getSnapshotJson())
                .setSortNo(entry.getSortNo())
                .setAttribute(entry.getAttribute());
    }

    private void replaceDirectory(Path target, Path source) throws IOException {
        if (Files.exists(target)) {
            deleteRecursively(target);
        }
        Files.createDirectories(target);
        try (java.util.stream.Stream<Path> children = Files.list(source)) {
            for (Path child : children.toList()) {
                copyPath(child, target.resolve(child.getFileName().toString()).normalize());
            }
        }
    }

    private void copyPath(Path source, Path target) throws IOException {
        if (Files.isDirectory(source)) {
            Files.createDirectories(target);
            try (java.util.stream.Stream<Path> children = Files.list(source)) {
                for (Path child : children.toList()) {
                    copyPath(child, target.resolve(child.getFileName().toString()).normalize());
                }
            }
            return;
        }
        Files.createDirectories(target.getParent());
        Files.copy(source, target, StandardCopyOption.REPLACE_EXISTING);
    }

    private void deleteRecursively(Path path) throws IOException {
        try (java.util.stream.Stream<Path> paths = Files.walk(path)) {
            for (Path item : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(item);
            }
        }
    }

    /** Build 恢复结果，只供工作区 Service 刷新摘要和响应字段。 */
    @Data
    @AllArgsConstructor
    public static class BuildRestoreResult {
        private ReleaseBuild build;
        private int restoredFileCount;
        private int restoredRelationCount;
    }
}
