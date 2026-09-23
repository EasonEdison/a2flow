package dev.a2flow.management.release;

import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.release.ReleaseModels.ReleaseBuild;
import dev.a2flow.management.release.ReleaseModels.ReleaseChange;
import dev.a2flow.management.release.ReleaseModels.ReleaseDeployment;
import dev.a2flow.management.release.ReleaseModels.ReleaseValidationEvidence;
import dev.a2flow.management.release.ReleaseModels.ReleaseVersion;

import lombok.extern.slf4j.Slf4j;

/**
 * ONLINE 原流水冻结来源校验与正式版本构造。
 *
 * <p>只为明确支持幂等重放的 Adapter 提供恢复来源，不重新选择草稿或最新 Build。
 * 主服务在校验后仍走同一套授权、审批、准出、发布和原子封板流程；本类不执行外部副作用或写库。
 */
@Slf4j
final class ReleaseOnlineRecovery {
    private static final String ACTIVE = "ACTIVE";
    private static final String SUCCEEDED = "SUCCEEDED";
    private static final String SOURCE_BUILD = "BUILD";
    private static final String ERROR_SOURCE = "online recovery source is invalid";
    private static final String VERSION_PREFIX = "version_";
    private static final String UUID_SEPARATOR = "-";

    private ReleaseOnlineRecovery() {
    }

    /** 校验原 Deployment 与冻结成功 Build、活动 Change 和预期摘要绑定一致。 */
    static ReleaseBuild requireBuild(AssetReleaseState state, ReleaseDeployment deployment,
            String expectedDigest, boolean forcePublish) {
        ReleaseBuild build = state.getBuilds().stream()
                .filter(item -> StringUtils.equals(item.getBuildId(), deployment.getSourceId()))
                .findFirst().orElseThrow(() -> new IllegalStateException(ERROR_SOURCE));
        ReleaseChange change = state.getActiveChange();
        if (!SOURCE_BUILD.equals(deployment.getSourceType()) || !SUCCEEDED.equals(build.getStatus())
                || !Objects.equals(build.getSourceDigest(), deployment.getSourceDigest())
                || !Objects.equals(build.getTargetVersion(), deployment.getSourceVersion())
                || build.getSnapshot() == null || change == null || !ACTIVE.equals(change.getStatus())
                || !Objects.equals(change.getChangeId(), build.getChangeId())
                || !Objects.equals(change.getTargetVersion(), build.getTargetVersion())
                || !Objects.equals(inputDigest(build), expectedDigest)
                || Boolean.TRUE.equals(deployment.getForced()) != forcePublish
                || state.getVersions().stream().anyMatch(version ->
                        Objects.equals(version.getVersion(), build.getTargetVersion()))) {
            throw new IllegalStateException(ERROR_SOURCE);
        }
        log.info("共享发布恢复ONLINE冻结来源, assetType:{}, assetKey:{}, buildId:{}, deploymentId:{}",
                state.getAssetType(), state.getAssetKey(), build.getBuildId(), deployment.getDeploymentId());
        return build;
    }

    /** 沿用既有 Version 身份与冻结字段；快照是否拆行由 Repository 统一处理。 */
    static ReleaseVersion sealVersion(ReleaseChange change, ReleaseBuild build, ReleaseArtifact artifact,
            Map<String, ReleaseValidationEvidence> validations, String operator) {
        return new ReleaseVersion()
                .setVersion(change.getTargetVersion())
                .setVersionId(VERSION_PREFIX + UUID.randomUUID().toString().replace(UUID_SEPARATOR, StringUtils.EMPTY))
                .setSourceBuildId(build.getBuildId())
                .setInputDigest(inputDigest(build))
                .setSourceDigest(build.getSourceDigest())
                .setSnapshot(build.getSnapshot())
                .setArtifact(artifact)
                .setValidations(validations)
                .setOperator(operator)
                .setCreateTime(System.currentTimeMillis());
    }

    private static String inputDigest(ReleaseBuild build) {
        return StringUtils.defaultIfBlank(build.getInputDigest(), build.getSourceDigest());
    }
}
