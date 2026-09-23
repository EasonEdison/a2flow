package dev.a2flow.management.release;

import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.function.BiConsumer;
import java.util.function.Function;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.ReleaseModels.EnvironmentState;
import dev.a2flow.management.release.ReleaseModels.GrayReleaseRule;
import dev.a2flow.management.release.ReleaseModels.PublishResult;
import dev.a2flow.management.release.ReleaseModels.ReleaseBuild;
import dev.a2flow.management.release.ReleaseModels.ReleaseDeployment;
import dev.a2flow.management.release.ReleaseModels.ReleasePointer;
import dev.a2flow.management.release.ReleaseModels.ReleasePublishContext;

import lombok.AccessLevel;
import lombok.NoArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 共享发布进行中流水的受控恢复器。
 *
 * <p>上游仅允许已显式声明无副作用重放的 Adapter 调用；本类只消费原 Deployment 指向的冻结 Build，
 * 校验身份后复用原流水执行领域发布并更新内存聚合，不创建新 Build/Deployment，也不读取当前草稿。
 */
@Slf4j
@NoArgsConstructor(access = AccessLevel.PRIVATE)
final class ReleasePublishingRecovery {

    private static final String SOURCE_BUILD = "BUILD";
    private static final String STATUS_PUBLISHING = "PUBLISHING";
    private static final String STATUS_SUCCEEDED = "SUCCEEDED";
    private static final String STATUS_FAILED = "FAILED";
    private static final String STATUS_STABLE = "STABLE";
    private static final String STATUS_GRAYING = "GRAYING";
    private static final String CURRENT_STAGE_SUPERSEDED = "SUPERSEDED";
    private static final String PUBLISH_MODE_GRAY = "GRAY";
    private static final String ERROR_PREPROD_PUBLICATION_SUPERSEDED = "PREPROD_PUBLICATION_SUPERSEDED";
    private static final String MESSAGE_PREPROD_PUBLICATION_SUPERSEDED = "已被新的预发发布请求覆盖";
    private static final String ERROR_RECOVERY_SOURCE_INVALID = "publishing recovery source is invalid";

    static ReleasePublishContext context(String assetKey, Map<String, String> params,
            ReleaseEnvironment environment, String requestId, String userName) {
        return new ReleasePublishContext()
                .setUserName(userName)
                .setAssetKey(assetKey)
                .setEnvironment(environment)
                .setRequestId(requestId)
                .setParams(new HashMap<>(params));
    }

    /**
     * PRT 采用最新请求优先：关闭不同 requestId 的遗留发布流水并清理其候选，不影响 ONLINE。
     */
    static void supersedePreprod(AssetReleaseState state,
            ReleaseEnvironment environment, String requestId, String assetKey, String userName) {
        if (environment != ReleaseEnvironment.PRT) {
            return;
        }
        ReleaseDeployment deployment = state.getDeployments().stream()
                .filter(item -> StringUtils.equals(item.getEnvironment(), environment.name()))
                .max(Comparator.comparing(ReleasePublishingRecovery::deploymentTimestamp))
                .orElse(null);
        if (deployment == null
                || !StringUtils.equals(deployment.getStatus(), STATUS_PUBLISHING)
                || StringUtils.equals(deployment.getRequestId(), requestId)) {
            return;
        }
        long now = System.currentTimeMillis();
        state.getBuilds().stream()
                .filter(item -> StringUtils.equals(item.getBuildId(), deployment.getSourceId()))
                .filter(item -> StringUtils.equals(item.getStatus(), STATUS_PUBLISHING))
                .findFirst()
                .ifPresent(build -> build.setStatus(STATUS_FAILED));
        deployment.setStatus(STATUS_FAILED)
                .setCurrentStage(CURRENT_STAGE_SUPERSEDED)
                .setRetryable(false)
                .setErrorCode(ERROR_PREPROD_PUBLICATION_SUPERSEDED)
                .setMessage(MESSAGE_PREPROD_PUBLICATION_SUPERSEDED)
                .setUpdateTime(now);
        EnvironmentState environmentState = state.getEnvironments().get(environment.name());
        if (environmentState != null && matches(environmentState.getCandidate(), deployment)) {
            environmentState.setCandidate(null).setGrayRule(null).setGrayStatus(STATUS_STABLE);
        }
        log.warn("共享发布预发旧流水被新请求覆盖, assetKey:{}, environment:{}, buildId:{}, "
                        + "deploymentId:{}, oldRequestId:{}, newRequestId:{}, operator:{}",
                assetKey, environment, deployment.getSourceId(), deployment.getDeploymentId(),
                deployment.getRequestId(), requestId, userName);
    }

    /** 只有 PRT 灰度、原流水仍在发布中且 Adapter 明确允许重放时才恢复。 */
    static boolean canRecoverGray(ReleaseEnvironment environment, ReleaseDeployment deployment,
            ReleaseAssetAdapter adapter) {
        return environment == ReleaseEnvironment.PRT
                && StringUtils.equals(deployment.getStatus(), STATUS_PUBLISHING)
                && adapter.supportsPublishingRecovery();
    }

    static ReleaseDeployment recover(
            AssetReleaseState state, ReleaseDeployment deployment, ReleasePublishContext context,
            Function<ReleasePublishContext, PublishResult> publisher,
            BiConsumer<ReleaseDeployment, PublishResult> resultApplier) {
        ReleaseBuild build = requireBuild(state, deployment, context);
        ReleaseDeployment recovered = recoverPublishing(
                deployment, build, context, publisher, resultApplier);
        if (StringUtils.equals(recovered.getStatus(), STATUS_SUCCEEDED)) {
            state.getEnvironments().put(context.getEnvironment().name(), new EnvironmentState()
                    .setEnvironment(context.getEnvironment().name())
                    .setSourceType(SOURCE_BUILD)
                    .setSourceId(build.getBuildId())
                    .setVersion(build.getTargetVersion())
                    .setDigest(build.getSourceDigest())
                    .setDeploymentId(deployment.getDeploymentId())
                    .setUpdateTime(System.currentTimeMillis()));
        }
        return recovered;
    }

    /** 灰度恢复只完成原流水发布，不推进 stable 指针；成功后按原灰度规则恢复 candidate。 */
    static ReleaseDeployment recoverGray(
            AssetReleaseState state, ReleaseDeployment deployment, GrayReleaseRule grayRule,
            ReleasePublishContext context,
            Function<ReleasePublishContext, PublishResult> publisher,
            BiConsumer<ReleaseDeployment, PublishResult> resultApplier) {
        if (!StringUtils.equals(deployment.getPublishMode(), PUBLISH_MODE_GRAY)) {
            throw new IllegalStateException(ERROR_RECOVERY_SOURCE_INVALID);
        }
        ReleaseBuild build = requireBuild(state, deployment, context);
        ReleaseDeployment recovered = recoverPublishing(
                deployment, build, context, publisher, resultApplier);
        if (StringUtils.equals(recovered.getStatus(), STATUS_SUCCEEDED)) {
            restoreGrayCandidate(state, recovered, build, grayRule, context);
        }
        return recovered;
    }

    private static void restoreGrayCandidate(AssetReleaseState state, ReleaseDeployment deployment,
            ReleaseBuild build, GrayReleaseRule grayRule, ReleasePublishContext context) {
        EnvironmentState environmentState = state.getEnvironments().get(context.getEnvironment().name());
        if (environmentState == null) {
            throw new IllegalStateException(ERROR_RECOVERY_SOURCE_INVALID);
        }
        environmentState.setCandidate(new ReleasePointer()
                        .setSourceType(SOURCE_BUILD)
                        .setSourceId(build.getBuildId())
                        .setVersion(build.getTargetVersion())
                        .setDigest(build.getSourceDigest())
                        .setDeploymentId(deployment.getDeploymentId())
                        .setUpdateTime(System.currentTimeMillis()))
                .setGrayRule(grayRule)
                .setGrayStatus(STATUS_GRAYING);
        log.info("共享发布恢复预发灰度候选完成, assetKey:{}, buildId:{}, deploymentId:{}, percentage:{}, "
                        + "requestId:{}, operator:{}",
                context.getAssetKey(), build.getBuildId(), deployment.getDeploymentId(), grayRule.getPercentage(),
                context.getRequestId(), context.getUserName());
    }

    private static ReleaseDeployment recoverPublishing(
            ReleaseDeployment deployment, ReleaseBuild build, ReleasePublishContext context,
            Function<ReleasePublishContext, PublishResult> publisher,
            BiConsumer<ReleaseDeployment, PublishResult> resultApplier) {
        context
                .setSourceType(SOURCE_BUILD)
                .setSourceId(build.getBuildId())
                .setSourceVersion(build.getTargetVersion())
                .setSnapshot(build.getSnapshot())
                .setArtifact(build.getArtifact());
        PublishResult publishResult = publisher.apply(context);
        resultApplier.accept(deployment, publishResult);
        build.setStatus(deployment.getStatus()).setArtifact(publishResult.getArtifact());
        log.info("共享发布恢复原流水完成, assetKey:{}, environment:{}, buildId:{}, deploymentId:{}, "
                        + "status:{}, requestId:{}, operator:{}",
                context.getAssetKey(), context.getEnvironment(), build.getBuildId(), deployment.getDeploymentId(),
                deployment.getStatus(), context.getRequestId(), context.getUserName());
        return deployment;
    }

    private static ReleaseBuild requireBuild(AssetReleaseState state, ReleaseDeployment deployment,
            ReleasePublishContext context) {
        if (!StringUtils.equals(deployment.getStatus(), STATUS_PUBLISHING)
                || !StringUtils.equals(deployment.getSourceType(), SOURCE_BUILD)
                || context.getEnvironment() == null
                || !StringUtils.equals(deployment.getEnvironment(), context.getEnvironment().name())
                || !StringUtils.equals(deployment.getRequestId(), context.getRequestId())
                || StringUtils.isBlank(deployment.getSourceId())) {
            throw new IllegalStateException(ERROR_RECOVERY_SOURCE_INVALID);
        }
        ReleaseBuild build = state.getBuilds().stream()
                .filter(item -> StringUtils.equals(item.getBuildId(), deployment.getSourceId()))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(ERROR_RECOVERY_SOURCE_INVALID));
        if (!StringUtils.equals(build.getStatus(), STATUS_PUBLISHING)
                || !Objects.equals(build.getTargetVersion(), deployment.getSourceVersion())
                || !StringUtils.equals(build.getSourceDigest(), deployment.getSourceDigest())
                || build.getSnapshot() == null) {
            throw new IllegalStateException(ERROR_RECOVERY_SOURCE_INVALID);
        }
        return build;
    }

    private static boolean matches(ReleasePointer candidate, ReleaseDeployment deployment) {
        if (candidate == null) {
            return false;
        }
        if (StringUtils.isNotBlank(candidate.getDeploymentId())) {
            return StringUtils.equals(candidate.getDeploymentId(), deployment.getDeploymentId());
        }
        return StringUtils.equals(candidate.getSourceType(), deployment.getSourceType())
                && StringUtils.equals(candidate.getSourceId(), deployment.getSourceId())
                && Objects.equals(candidate.getVersion(), deployment.getSourceVersion())
                && StringUtils.equals(candidate.getDigest(), deployment.getSourceDigest());
    }

    private static long deploymentTimestamp(ReleaseDeployment deployment) {
        return Objects.requireNonNullElse(deployment.getUpdateTime(),
                Objects.requireNonNullElse(deployment.getCreateTime(), 0L));
    }
}
