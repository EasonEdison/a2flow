package dev.a2flow.management.release;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.lifecycle.SkillFactoryWorkspaceService;
import dev.a2flow.management.lifecycle.SkillPreprodBuildRestoreService;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.GateResult;
import dev.a2flow.management.release.ReleaseModels.PublishResult;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.release.ReleaseModels.ReleasePublishContext;
import dev.a2flow.management.release.ReleaseModels.ReleaseRelationSnapshot;
import dev.a2flow.management.release.ReleaseModels.ReleaseValidationRequirement;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyPathNode;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyReleaseFailure;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyReleaseReport;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyValidationRequest;
import dev.a2flow.management.release.dependency.AssetDependencyReleaseValidator;
import dev.a2flow.management.release.diff.ReleaseDiffDocument;
import dev.a2flow.management.release.diff.ReleaseDiffEngine;
import dev.a2flow.management.release.diff.ReleaseDiffQuery;
import dev.a2flow.management.release.diff.ReleaseDiffResource;
import dev.a2flow.management.release.diff.SkillReleaseDiffResourceProvider;

import lombok.extern.slf4j.Slf4j;

/**
 * Skill 领域发布适配器。
 *
 * <p>当前快照来自真实 workspace 元信息；预发和线上部署复用 lifecycle 的 ZIP 构建/发布方法。
 * 历史重发只把共享控制面选中的数字版本转换成 `HISTORICAL + sourceVersion`，不创建版本、不修改
 * `preprod/current`，也不接管共享发布版本或产物目录。现有运行平台上传仍返回待接入状态时，
 * 本 Adapter 必须原样返回 PLATFORM_PENDING，不能推进共享 ONLINE 状态。
 */
@Component
@Slf4j
public class SkillReleaseAssetAdapter extends AbstractReleaseAssetAdapter {

    private static final String PARAM_SKILL_CODE = "skillCode";
    private static final String PARAM_WORKSPACE_ID = "workspaceId";
    private static final String PARAM_BASE_VERSION = "baseVersion";
    private static final String PARAM_PUBLISH_SOURCE_TYPE = "publishSourceType";
    private static final String PARAM_SOURCE_VERSION = "sourceVersion";
    private static final String FIELD_FILE_TREE_DIGEST = "fileTreeDigest";
    private static final String FIELD_SKILL_DESCRIPTION =
            SkillReleaseMetadataSupport.FIELD_SKILL_DESCRIPTION;
    private static final String FIELD_SKILL_NAME = "skillName";
    private static final String FIELD_SKILL_NAME_CN = "skillNameCn";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_STATUS = "status";
    private static final String FIELD_EDITABLE = "editable";
    private static final String FIELD_LANG_BRIDGE_SKILL_ID = "langBridgeSkillId";
    private static final String FIELD_PUBLISH_STATUS = "publishStatus";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_VERSION = "version";
    private static final String FIELD_ARTIFACT = "artifact";
    private static final String FIELD_EXTERNAL_PUBLISH_STAGE = "externalPublishStage";
    private static final String FIELD_RETRYABLE = "retryable";
    private static final String FIELD_ERROR_CODE = "errorCode";
    private static final String PUBLISH_STAGE_PREPROD = "PREPROD_PUBLISH";
    private static final String PACKAGE_TYPE_PREPROD_SNAPSHOT = "PREPROD_SNAPSHOT";
    private static final String SOURCE_TYPE_VERSION = "VERSION";
    private static final String PUBLISH_SOURCE_CURRENT = "CURRENT";
    private static final String PUBLISH_SOURCE_HISTORICAL = "HISTORICAL";
    private static final String PUBLISH_STATUS_SUCCEEDED = "SUCCEEDED";
    private static final String PUBLISH_STATUS_PLATFORM_PENDING = "PACKAGE_BUILT_PLATFORM_PENDING";
    private static final String ERROR_SOURCE_VERSION_REQUIRED = "Skill历史重发缺少数字版本";
    private static final String ERROR_RELEASE_VERSION_REQUIRED = "Skill正式版本快照缺少数字版本";
    private static final String ERROR_CHANGE_CREATE_FAILED = "Skill从正式版本新建变更失败";
    private static final String ERROR_PUBLISH_STATUS_UNKNOWN = "Skill发布返回未知状态";
    private static final String GATE_WORKSPACE_DIGEST = "SKILL_WORKSPACE_DIGEST";
    private static final String GATE_RELEASE_ARTIFACT = "SKILL_RELEASE_ARTIFACT";
    private static final String GATE_ASSET_DEPENDENCIES = "SKILL_ASSET_DEPENDENCIES";
    public static final String VALIDATION_SKILL_RELEASE_READINESS = "SKILL_RELEASE_READINESS";
    public static final String SKILL_RELEASE_READINESS_RULE_VERSION = "skill-release-readiness-v2";
    private static final String LABEL_WORKSPACE_DIGEST = "工作区摘要";
    private static final String LABEL_RELEASE_ARTIFACT = "正式包产物";
    private static final String LABEL_ASSET_DEPENDENCIES = "Skill资产依赖";
    private static final String LABEL_SKILL_RELEASE_READINESS = "Skill 综合准出";
    private static final String MESSAGE_DIGEST_READY = "工作区摘要已生成";
    private static final String MESSAGE_DIGEST_MISSING = "工作区摘要为空";
    private static final String MESSAGE_ARTIFACT_READY = "正式包地址已冻结";
    private static final String MESSAGE_ARTIFACT_PREPROD = "预发构建阶段生成包产物";
    private static final String MESSAGE_ARTIFACT_MISSING = "正式包地址为空";
    private static final String MESSAGE_DEPENDENCIES_READY = "Skill直接和间接资产依赖均可解析";
    private static final String PATH_SEPARATOR = " -> ";
    private static final String FAILURE_SEPARATOR = "; ";
    private static final String LABEL_CURRENT_CONTENT = "当前内容";
    private static final String LABEL_VERSION_PREFIX = "版本 ";

    @Resource
    private SkillFactoryWorkspaceService workspaceService;

    @Resource
    private SkillReleaseDiffResourceProvider diffResourceProvider;

    @Resource
    private ReleaseDiffEngine releaseDiffEngine;

    @Resource
    private SkillReleaseBindingSnapshotReader bindingSnapshotReader;

    @Resource
    private AssetDependencyReleaseValidator assetDependencyReleaseValidator;

    @Resource
    private SkillDependencyReleaseAuditService dependencyReleaseAuditService;

    @Resource
    private SkillPreprodBuildRestoreService preprodBuildRestoreService;

    @Override
    public ReleaseAssetType assetType() {
        return ReleaseAssetType.SKILL;
    }

    /** 从 skillCode 对应 workspace 读取真实文件摘要和基础信息。 */
    @Override
    public AssetSnapshot currentSnapshot(String assetKey, Map<String, String> params) {
        Map<String, Object> detail = workspaceService.skillDetail(assetKey, params);
        Object digestValue = detail.get(FIELD_FILE_TREE_DIGEST);
        String fileTreeDigest = digestValue == null ? StringUtils.EMPTY : String.valueOf(digestValue);
        String skillDescription = stringValue(detail.get(FIELD_SKILL_DESCRIPTION));
        String digest = SkillReleaseMetadataSupport.sourceDigest(
                fileTreeDigest, skillDescription, detail);
        return snapshot(assetKey, detail, summaryEntry(
                FIELD_SKILL_NAME, detail.get(FIELD_SKILL_NAME_CN),
                FIELD_SKILL_CODE, detail.get(FIELD_SKILL_CODE),
                FIELD_WORKSPACE_ID, detail.get(FIELD_WORKSPACE_ID),
                FIELD_SKILL_DESCRIPTION, skillDescription,
                FIELD_VERSION, detail.get(FIELD_VERSION),
                FIELD_STATUS, detail.get(FIELD_STATUS),
                FIELD_EDITABLE, detail.get(FIELD_EDITABLE),
                FIELD_LANG_BRIDGE_SKILL_ID, detail.get(FIELD_LANG_BRIDGE_SKILL_ID)), digest,
                StringUtils.EMPTY);
    }

    /**
     * 新注册 Skill 的 lifecycle 编辑态就是首个可编辑变更。
     *
     * <p>这里只声明领域事实，不创建共享状态；共享控制面会同时确认没有历史正式版本，并在首次 PRT
     * 发布的资产锁内持久化 ACTIVE change。封板后的下一轮变更仍必须显式调用 RELEASE_CHANGE_CREATE。
     */
    @Override
    public boolean isInitialEditableChange(AssetSnapshot snapshot) {
        Object editable = snapshot.getSummary() == null ? null : snapshot.getSummary().get(FIELD_EDITABLE);
        return Boolean.TRUE.equals(editable)
                || StringUtils.equalsIgnoreCase(Boolean.TRUE.toString(), String.valueOf(editable));
    }

    /** 把两个环境的完整依赖解析审计写入 Skill Build，不修改当前 workspace。 */
    @Override
    public AssetSnapshot freezeBuildSnapshot(
            String assetKey, AssetSnapshot current, Map<String, String> params) {
        return dependencyReleaseAuditService.freeze(assetKey, current);
    }

    /** 冻结当前 Skill 数字版本的全部通用关系，供成功 PRT Build 后续完整恢复。 */
    @Override
    public ReleaseRelationSnapshot freezeBuildRelationSnapshot(
            String assetKey, AssetSnapshot snapshot, Map<String, String> params) {
        return preprodBuildRestoreService.freezeCurrentRelations(assetKey);
    }

    /**
     * 使用 Skill lifecycle 提供的安全文件资源，并由共享引擎计算行级 Diff。
     *
     * <p>正式版本快照中的 `version` 是共享发布控制面封板时的数字版本。这里仅把目标版本交给
     * lifecycle 读取 `online/releases/{version}`；lifecycle 不再自行计算或拼装 Map 结果。
     */
    @Override
    public ReleaseDiffDocument diff(AssetSnapshot current, AssetSnapshot target, ReleaseDiffQuery query) {
        Object targetVersion = target.getSummary().get(FIELD_VERSION);
        if (targetVersion == null || StringUtils.isBlank(String.valueOf(targetVersion))) {
            throw new IllegalStateException(ERROR_RELEASE_VERSION_REQUIRED);
        }
        Integer version = Integer.valueOf(String.valueOf(targetVersion));
        Map<String, String> diffParams = new HashMap<>();
        diffParams.put(PARAM_WORKSPACE_ID, current.getAssetKey());
        diffParams.put(PARAM_SKILL_CODE, current.getAssetKey());
        log.info("Skill领域开始读取发布Diff资源, skillCode:{}, compareVersion:{}, entryPath:{}",
                current.getAssetKey(), version, query == null ? null : query.getEntryPath());
        List<ReleaseDiffResource> currentResources = withMetadataResource(current,
                diffResourceProvider.currentResources(current.getAssetKey(), diffParams));
        List<ReleaseDiffResource> versionResources = withMetadataResource(target,
                diffResourceProvider.versionResources(current.getAssetKey(), version, target, diffParams));
        return releaseDiffEngine.compare(LABEL_VERSION_PREFIX + version, LABEL_CURRENT_CONTENT,
                versionResources, currentResources, query);
    }

    /** Skill 预发要求 workspace 摘要存在；线上和历史重发还必须携带已冻结 ZIP 地址。 */
    @Override
    public List<GateResult> evaluateGates(String assetKey, ReleaseEnvironment environment,
            AssetSnapshot snapshot, Map<String, String> params) {
        return evaluateGates(assetKey, environment, snapshot, null, params);
    }

    /** 使用共享 Build/Version 中的结构化 ZIP 产物执行线上门禁。 */
    @Override
    public List<GateResult> evaluateGates(String assetKey, ReleaseEnvironment environment,
            AssetSnapshot snapshot, ReleaseArtifact artifact, Map<String, String> params) {
        boolean digestReady = StringUtils.isNotBlank(snapshot.getDigest());
        boolean artifactReady = environment == ReleaseEnvironment.PRT
                || artifact != null && StringUtils.isNotBlank(artifact.getPackageDigest())
                        && (StringUtils.isNotBlank(artifact.getObjectKey())
                                || StringUtils.isNotBlank(artifact.getPackageUrl()));
        GateResult workspaceGate = gate(GATE_WORKSPACE_DIGEST, LABEL_WORKSPACE_DIGEST, digestReady, true,
                digestReady ? MESSAGE_DIGEST_READY : MESSAGE_DIGEST_MISSING);
        GateResult artifactGate = gate(GATE_RELEASE_ARTIFACT, LABEL_RELEASE_ARTIFACT, artifactReady,
                environment == ReleaseEnvironment.ONLINE,
                artifactReady && environment == ReleaseEnvironment.ONLINE ? MESSAGE_ARTIFACT_READY
                        : environment == ReleaseEnvironment.PRT
                                ? MESSAGE_ARTIFACT_PREPROD : MESSAGE_ARTIFACT_MISSING);
        DependencyReleaseReport dependencyReport = assetDependencyReleaseValidator.validate(
                dependencyValidationRequest(assetKey, environment, snapshot));
        boolean dependenciesReady = Boolean.TRUE.equals(dependencyReport.getPassed());
        GateResult dependencyGate = gate(GATE_ASSET_DEPENDENCIES, LABEL_ASSET_DEPENDENCIES,
                dependenciesReady, true, dependenciesReady ? MESSAGE_DEPENDENCIES_READY
                        : dependencyFailureMessage(dependencyReport.getFailures()));
        return List.of(workspaceGate, artifactGate, dependencyGate);
    }

    private DependencyValidationRequest dependencyValidationRequest(String assetKey,
            ReleaseEnvironment environment, AssetSnapshot snapshot) {
        List<AssetDependencyReference> dependencies = bindingSnapshotReader.readDirectDependencies(snapshot)
                .stream()
                .map(this::dependencyReference)
                .toList();
        return new DependencyValidationRequest()
                .setRootAssetType(ReleaseAssetType.SKILL.name())
                .setRootAssetKey(assetKey)
                .setRequestedEnvironment(environment)
                .setDependencies(dependencies);
    }

    private AssetDependencyReference dependencyReference(
            SkillReleaseBindingSnapshotReader.DirectDependency dependency) {
        return new AssetDependencyReference()
                .setAssetType(dependency.getAssetType())
                .setAssetKey(dependency.getAssetKey());
    }

    private String dependencyFailureMessage(List<DependencyReleaseFailure> failures) {
        return failures.stream()
                .map(failure -> dependencyPath(failure.getPath()) + ": [" + failure.getErrorCode()
                        + "] " + StringUtils.defaultString(failure.getMessage()))
                .collect(java.util.stream.Collectors.joining(FAILURE_SEPARATOR));
    }

    private String dependencyPath(List<DependencyPathNode> path) {
        return path.stream()
                .map(node -> node.getAssetType() + "/" + node.getAssetKey())
                .collect(java.util.stream.Collectors.joining(PATH_SEPARATOR));
    }

    /**
     * Manual-entry management does not require suspended AI inspection evidence.
     * Deterministic file, contract and target-dependency gates remain in evaluateGates.
     * This does not create or mark any AI inspection evidence as passed.
     */
    @Override
    public List<ReleaseValidationRequirement> validationRequirements(ReleaseEnvironment environment) {
        return List.of();
    }

    /**
     * 通过 lifecycle 新建变更入口恢复历史版本。
     *
     * <p>共享控制面负责选择 baseVersion；lifecycle 负责复制正式目录、推进 Skill 数字版本并复制
     * entity_relation。这里不直接解压 ZIP，避免共享状态和 Skill 草稿状态分叉。
     */
    @Override
    public void restore(String userName, String assetKey, AssetSnapshot snapshot, Map<String, String> params) {
        try {
            params.put(PARAM_SKILL_CODE, assetKey);
            params.put(PARAM_WORKSPACE_ID, assetKey);
            Object version = snapshot.getSummary() == null ? null : snapshot.getSummary().get(FIELD_VERSION);
            if (StringUtils.isBlank(params.get(PARAM_BASE_VERSION)) && version != null) {
                params.put(PARAM_BASE_VERSION, String.valueOf(version));
            }
            log.info("Skill领域从正式版本新建变更, skillCode:{}, baseVersion:{}, operator:{}",
                    assetKey, params.get(PARAM_BASE_VERSION), userName);
            workspaceService.createChange(assetKey, params);
        } catch (IOException e) {
            throw new IllegalStateException(ERROR_CHANGE_CREATE_FAILED, e);
        }
    }

    /**
     * 复用 lifecycle ZIP 发布入口；历史重发强制使用所选数字版本，绝不读取当前工作区作为来源。
     */
    @Override
    public PublishResult deploy(ReleasePublishContext context) {
        dev.a2flow.management.lifecycle.publish.SkillPublicationInput publicationInput =
                new dev.a2flow.management.lifecycle.publish.SkillPublicationInput(
                        context.getSourceId(), context.getSnapshot().getDigest(),
                        context.getSnapshot().getPayloadJson(), context.getRequestId());
        Map<String, String> publishParams = new HashMap<>(context.getParams());
        String assetKey = context.getAssetKey();
        try {
            publishParams.put(PARAM_SKILL_CODE, assetKey);
            publishParams.put(PARAM_WORKSPACE_ID, assetKey);
            publishParams.put(FIELD_SKILL_DESCRIPTION,
                    SkillReleaseMetadataSupport.requireSkillDescription(context.getSnapshot()));
            boolean historical = StringUtils.equals(context.getSourceType(), SOURCE_TYPE_VERSION);
            if (historical) {
                if (context.getSourceVersion() == null || context.getSourceVersion() <= 0) {
                    return failed(ERROR_SOURCE_VERSION_REQUIRED);
                }
                publishParams.put(PARAM_PUBLISH_SOURCE_TYPE, PUBLISH_SOURCE_HISTORICAL);
                publishParams.put(PARAM_SOURCE_VERSION, String.valueOf(context.getSourceVersion()));
            } else if (context.getEnvironment() == ReleaseEnvironment.ONLINE) {
                publishParams.put(PARAM_PUBLISH_SOURCE_TYPE, PUBLISH_SOURCE_CURRENT);
                publishParams.put(PARAM_SOURCE_VERSION, String.valueOf(context.getSourceVersion()));
            }
            log.info("Skill领域发布开始, skillCode:{}, environment:{}, sourceType:{}, sourceVersion:{}, "
                            + "requestId:{}",
                    assetKey, context.getEnvironment(), context.getSourceType(), context.getSourceVersion(),
                    context.getRequestId());
            Map<String, Object> result = context.getEnvironment() == ReleaseEnvironment.PRT
                    ? workspaceService.publishPreprodPackage(assetKey, publishParams,
                            context.getPreviousDeployment(), publicationInput)
                    : workspaceService.publishOnlinePackage(assetKey, publishParams, context.getArtifact(),
                            context.getPreviousDeployment(), context.getRequestId(), publicationInput);
            String publishStatus = stringValue(result.get(FIELD_PUBLISH_STATUS));
            String message = stringValue(result.get(FIELD_MESSAGE));
            ReleaseArtifact resultArtifact = result.get(FIELD_ARTIFACT) instanceof ReleaseArtifact
                    ? (ReleaseArtifact) result.get(FIELD_ARTIFACT) : context.getArtifact();
            String stage = stringValue(result.get(FIELD_EXTERNAL_PUBLISH_STAGE));
            boolean retryable = Boolean.TRUE.equals(result.get(FIELD_RETRYABLE));
            String errorCode = stringValue(result.get(FIELD_ERROR_CODE));
            log.info("Skill领域发布完成, skillCode:{}, sourceVersion:{}, publishStatus:{}, requestId:{}",
                    assetKey, context.getSourceVersion(), publishStatus, context.getRequestId());
            if (StringUtils.equals(publishStatus, PUBLISH_STATUS_SUCCEEDED)) {
                return result(publishStatus, stage, retryable, errorCode, message, resultArtifact, result);
            }
            if (StringUtils.equals(publishStatus, PUBLISH_STATUS_PLATFORM_PENDING)) {
                return result(DEPLOYMENT_PLATFORM_PENDING, stage, retryable, errorCode,
                        message, resultArtifact, result);
            }
            return result(StringUtils.defaultIfBlank(publishStatus, DEPLOYMENT_FAILED), stage, retryable,
                    errorCode, StringUtils.defaultIfBlank(message,
                            ERROR_PUBLISH_STATUS_UNKNOWN + ": " + publishStatus), resultArtifact, result);
        } catch (IOException e) {
            log.warn("Skill领域发布失败, skillCode:{}, sourceVersion:{}, requestId:{}",
                    assetKey, context.getSourceVersion(), context.getRequestId(), e);
            return failed("Skill ZIP 构建失败: " + e.getMessage());
        }
    }

    private PublishResult result(String status, String stage, boolean retryable, String errorCode,
            String message, ReleaseArtifact artifact, Map<String, Object> data) {
        return new PublishResult()
                .setStatus(status)
                .setCurrentStage(stage)
                .setRetryable(retryable)
                .setErrorCode(StringUtils.defaultString(errorCode))
                .setMessage(StringUtils.defaultString(message))
                .setArtifact(artifact)
                .setData(data);
    }

    private String stringValue(Object value) {
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }

    private List<ReleaseDiffResource> withMetadataResource(AssetSnapshot snapshot,
            List<ReleaseDiffResource> fileResources) {
        List<ReleaseDiffResource> resources = new ArrayList<>(fileResources.size() + 1);
        resources.add(SkillReleaseMetadataSupport.diffResource(snapshot));
        resources.addAll(fileResources);
        return resources;
    }
}
