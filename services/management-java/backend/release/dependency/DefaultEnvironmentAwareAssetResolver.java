package dev.a2flow.management.release.dependency;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.release.GrayRouteReason;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.EnvironmentState;
import dev.a2flow.management.release.ReleaseModels.GrayReleaseRule;
import dev.a2flow.management.release.ReleaseModels.ReleaseBuild;
import dev.a2flow.management.release.ReleaseModels.ReleasePointer;
import dev.a2flow.management.release.ReleaseModels.ReleaseVersion;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetResolutionContext;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.storage.db.repository.AssetReleaseStateRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * 基于共享发布聚合的环境感知资产解析器。
 *
 * <p>上游传入稳定依赖身份、可信环境和可选可信 userId，本类只读取 AssetReleaseState Repository，
 * 按固定优先级选择 stable/candidate，再严格核对 Build/Version 身份、数字版本、摘要和不可变快照，
 * 最后委托领域 Adapter 判断 enabled。它不解析领域 payload，也不读取当前草稿、最大版本或另一指针
 * 作为损坏指针的兜底。
 */
@Service
@Slf4j
public class DefaultEnvironmentAwareAssetResolver implements EnvironmentAwareAssetResolver {

    private static final String STATUS_SUCCEEDED = "SUCCEEDED";
    private static final int DIGEST_LOG_PREFIX_LENGTH = 16;

    private static final String MESSAGE_ENVIRONMENT_REQUIRED = "发布环境不能为空";
    private static final String MESSAGE_REFERENCE_INVALID = "依赖资产类型和assetKey不能为空";
    private static final String MESSAGE_ADAPTER_MISSING = "依赖资产类型尚未注册领域Adapter";
    private static final String MESSAGE_RELEASE_NOT_AVAILABLE = "资产没有可用的PRT或ONLINE发布版本";
    private static final String MESSAGE_PREPROD_POINTER_INVALID = "PRT指针或Build快照不完整";
    private static final String MESSAGE_ONLINE_POINTER_REQUIRED = "资产尚未发布ONLINE版本";
    private static final String MESSAGE_ONLINE_POINTER_INVALID = "ONLINE指针或Version快照不完整";
    private static final String MESSAGE_ASSET_DISABLED = "不可变发布快照对应的资产已禁用";
    private static final int FULL_PERCENTAGE = 100;
    private static final int MIN_PERCENTAGE = 0;
    private static final int USER_BUCKET_COUNT = 100;
    private static final String STATUS_STABLE = "STABLE";
    private static final String STATUS_GRAYING = "GRAYING";

    private final AssetReleaseStateRepository assetReleaseStateRepository;
    private final AssetDependencyAdapterRegistry adapterRegistry;

    public DefaultEnvironmentAwareAssetResolver(AssetReleaseStateRepository assetReleaseStateRepository,
            AssetDependencyAdapterRegistry adapterRegistry) {
        this.assetReleaseStateRepository = assetReleaseStateRepository;
        this.adapterRegistry = adapterRegistry;
    }

    /**
     * 按可信环境解析一个稳定资产身份。
     *
     * <p>PRT Map 中完全没有 PRT key 时才尝试 ONLINE；只要 key 存在，即使值为空，也按
     * 损坏 PRT 指针失败，避免掩盖发布状态损坏。
     */
    @Override
    public ResolvedReleasedAsset resolve(AssetDependencyReference dependency,
            AssetResolutionContext context) {
        ReleaseEnvironment requestedEnvironment = context == null ? null : context.getRequestedEnvironment();
        validateRequest(dependency, requestedEnvironment);
        AssetDependencyAdapter adapter = requireAdapter(dependency, requestedEnvironment);
        ReleaseAssetType releaseAssetType = adapter.releaseAssetType();
        if (releaseAssetType == null) {
            throw failure(AssetDependencyErrorCode.ASSET_TYPE_UNSUPPORTED, dependency,
                    requestedEnvironment, MESSAGE_ADAPTER_MISSING);
        }
        AssetReleaseState state = assetReleaseStateRepository.find(releaseAssetType, dependency.getAssetKey());
        return resolveFromState(dependency, context, state);
    }

    /** 复用当次分页加载的聚合；入口核对资产身份，后续沿用单项查询的环境和不可变来源校验。 */
    @Override
    public ResolvedReleasedAsset resolveFromState(AssetDependencyReference dependency,
            AssetResolutionContext context, AssetReleaseState state) {
        ReleaseEnvironment requestedEnvironment = context == null ? null : context.getRequestedEnvironment();
        validateRequest(dependency, requestedEnvironment);
        AssetDependencyAdapter adapter = requireAdapter(dependency, requestedEnvironment);
        ReleaseAssetType releaseAssetType = adapter.releaseAssetType();
        if (releaseAssetType == null) {
            throw failure(AssetDependencyErrorCode.ASSET_TYPE_UNSUPPORTED, dependency,
                    requestedEnvironment, MESSAGE_ADAPTER_MISSING);
        }
        if (state == null || !StringUtils.equals(state.getAssetType(), releaseAssetType.name())
                || !StringUtils.equals(state.getAssetKey(), dependency.getAssetKey())) {
            throw failure(AssetDependencyErrorCode.ASSET_REFERENCE_INVALID, dependency,
                    requestedEnvironment, MESSAGE_REFERENCE_INVALID);
        }
        ResolvedReleasedAsset resolvedAsset = requestedEnvironment == ReleaseEnvironment.PRT
                ? resolvePreprod(state, dependency, context, releaseAssetType)
                : resolveOnline(state, dependency, requestedEnvironment, releaseAssetType,
                        AssetDependencyErrorCode.ONLINE_POINTER_REQUIRED, context);
        verifyEnabled(adapter, resolvedAsset, dependency, requestedEnvironment);
        log.info("环境资产解析完成, assetType:{}, assetKey:{}, requestedEnvironment:{}, "
                        + "resolvedEnvironment:{}, sourceType:{}, sourceId:{}, version:{}, candidate:{}, "
                        + "routeReason:{}, digestPrefix:{}",
                dependency.getAssetType(), dependency.getAssetKey(), requestedEnvironment,
                resolvedAsset.getResolvedEnvironment(), resolvedAsset.getSourceType(),
                resolvedAsset.getSourceId(), resolvedAsset.getVersion(), resolvedAsset.getCandidate(),
                resolvedAsset.getRouteReason(), digestPrefix(resolvedAsset.getDigest()));
        return resolvedAsset;
    }

    private void validateRequest(AssetDependencyReference dependency, ReleaseEnvironment requestedEnvironment) {
        if (requestedEnvironment == null) {
            throw failure(AssetDependencyErrorCode.RELEASE_ENVIRONMENT_REQUIRED, dependency, null,
                    MESSAGE_ENVIRONMENT_REQUIRED);
        }
        if (dependency == null || dependency.getAssetType() == null
                || StringUtils.isBlank(dependency.getAssetKey())) {
            throw failure(AssetDependencyErrorCode.ASSET_REFERENCE_INVALID, dependency,
                    requestedEnvironment, MESSAGE_REFERENCE_INVALID);
        }
    }

    private AssetDependencyAdapter requireAdapter(AssetDependencyReference dependency,
            ReleaseEnvironment requestedEnvironment) {
        return adapterRegistry.find(dependency.getAssetType())
                .orElseThrow(() -> failure(AssetDependencyErrorCode.ASSET_TYPE_UNSUPPORTED, dependency,
                        requestedEnvironment, MESSAGE_ADAPTER_MISSING));
    }

    private ResolvedReleasedAsset resolvePreprod(AssetReleaseState state, AssetDependencyReference dependency,
            AssetResolutionContext context, ReleaseAssetType releaseAssetType) {
        ReleaseEnvironment requestedEnvironment = context.getRequestedEnvironment();
        Map<String, EnvironmentState> environments = state == null ? null : state.getEnvironments();
        if (environments == null || !environments.containsKey(ReleaseEnvironment.PRT.name())) {
            return resolveOnline(state, dependency, requestedEnvironment, releaseAssetType,
                    AssetDependencyErrorCode.ASSET_RELEASE_NOT_AVAILABLE, context);
        }
        EnvironmentState environmentState = environments.get(ReleaseEnvironment.PRT.name());
        SelectedPointer selected = selectPointer(environmentState, context.getUserId(), dependency,
                requestedEnvironment, AssetDependencyErrorCode.PREPROD_POINTER_INVALID,
                MESSAGE_PREPROD_POINTER_INVALID);
        return resolveBuild(state, selected.pointer, dependency, requestedEnvironment, releaseAssetType)
                .setCandidate(selected.candidate)
                .setRouteReason(selected.routeReason);
    }

    private ResolvedReleasedAsset resolveBuild(AssetReleaseState state, EnvironmentState pointer,
            AssetDependencyReference dependency, ReleaseEnvironment requestedEnvironment,
            ReleaseAssetType releaseAssetType) {
        AssetDependencyErrorCode errorCode = AssetDependencyErrorCode.PREPROD_POINTER_INVALID;
        if (!validPointer(pointer, ReleaseEnvironment.PRT, ReleasedAssetSourceType.BUILD)) {
            throw failure(errorCode, dependency, requestedEnvironment, MESSAGE_PREPROD_POINTER_INVALID);
        }
        List<ReleaseBuild> matchedBuilds = state.getBuilds() == null ? List.of() : state.getBuilds().stream()
                .filter(build -> StringUtils.equals(build.getBuildId(), pointer.getSourceId()))
                .toList();
        if (matchedBuilds.size() != 1) {
            throw failure(errorCode, dependency, requestedEnvironment, MESSAGE_PREPROD_POINTER_INVALID);
        }
        ReleaseBuild build = matchedBuilds.get(0);
        if (!StringUtils.equals(build.getStatus(), STATUS_SUCCEEDED)
                || !Objects.equals(build.getTargetVersion(), pointer.getVersion())
                || !StringUtils.equals(build.getSourceDigest(), pointer.getDigest())
                || !validSnapshot(build.getSnapshot(), dependency.getAssetKey(), releaseAssetType,
                        build.getSourceDigest())) {
            throw failure(errorCode, dependency, requestedEnvironment, MESSAGE_PREPROD_POINTER_INVALID);
        }
        return resolved(dependency, requestedEnvironment, ReleaseEnvironment.PRT,
                ReleasedAssetSourceType.BUILD, build.getBuildId(), build.getTargetVersion(),
                build.getSnapshot());
    }

    private ResolvedReleasedAsset resolveOnline(AssetReleaseState state, AssetDependencyReference dependency,
            ReleaseEnvironment requestedEnvironment, ReleaseAssetType releaseAssetType,
            AssetDependencyErrorCode missingPointerCode, AssetResolutionContext context) {
        Map<String, EnvironmentState> environments = state == null ? null : state.getEnvironments();
        if (environments == null || !environments.containsKey(ReleaseEnvironment.ONLINE.name())) {
            String message = missingPointerCode == AssetDependencyErrorCode.ONLINE_POINTER_REQUIRED
                    ? MESSAGE_ONLINE_POINTER_REQUIRED : MESSAGE_RELEASE_NOT_AVAILABLE;
            throw failure(missingPointerCode, dependency, requestedEnvironment, message);
        }
        EnvironmentState environmentState = environments.get(ReleaseEnvironment.ONLINE.name());
        SelectedPointer selected = selectPointer(environmentState, context == null ? null : context.getUserId(),
                dependency, requestedEnvironment, AssetDependencyErrorCode.ONLINE_POINTER_INVALID,
                MESSAGE_ONLINE_POINTER_INVALID);
        EnvironmentState pointer = selected.pointer;
        if (!validPointer(pointer, ReleaseEnvironment.ONLINE, ReleasedAssetSourceType.VERSION)) {
            throw failure(AssetDependencyErrorCode.ONLINE_POINTER_INVALID, dependency,
                    requestedEnvironment, MESSAGE_ONLINE_POINTER_INVALID);
        }
        List<ReleaseVersion> matchedVersions = state.getVersions() == null ? List.of()
                : state.getVersions().stream()
                        .filter(version -> StringUtils.equals(version.getVersionId(), pointer.getSourceId()))
                        .toList();
        if (matchedVersions.size() != 1) {
            throw failure(AssetDependencyErrorCode.ONLINE_POINTER_INVALID, dependency,
                    requestedEnvironment, MESSAGE_ONLINE_POINTER_INVALID);
        }
        ReleaseVersion version = matchedVersions.get(0);
        if (!Objects.equals(version.getVersion(), pointer.getVersion())
                || !StringUtils.equals(version.getSourceDigest(), pointer.getDigest())
                || !validSnapshot(version.getSnapshot(), dependency.getAssetKey(), releaseAssetType,
                        version.getSourceDigest())) {
            throw failure(AssetDependencyErrorCode.ONLINE_POINTER_INVALID, dependency,
                    requestedEnvironment, MESSAGE_ONLINE_POINTER_INVALID);
        }
        return resolved(dependency, requestedEnvironment, ReleaseEnvironment.ONLINE,
                ReleasedAssetSourceType.VERSION, version.getVersionId(), version.getVersion(),
                version.getSnapshot())
                .setCandidate(selected.candidate)
                .setRouteReason(selected.routeReason);
    }

    private SelectedPointer selectPointer(EnvironmentState state, Long userId,
            AssetDependencyReference dependency, ReleaseEnvironment requestedEnvironment,
            AssetDependencyErrorCode errorCode, String errorMessage) {
        if (state == null) {
            throw failure(errorCode, dependency, requestedEnvironment, errorMessage);
        }
        ReleasePointer candidate = state.getCandidate();
        GrayReleaseRule rule = state.getGrayRule();
        if (candidate == null) {
            if (rule != null || (StringUtils.isNotBlank(state.getGrayStatus())
                    && !StringUtils.equals(state.getGrayStatus(), STATUS_STABLE))) {
                throw failure(errorCode, dependency, requestedEnvironment, errorMessage);
            }
            return new SelectedPointer(stablePointer(state), false, GrayRouteReason.NO_CANDIDATE);
        }
        if (!StringUtils.equals(state.getGrayStatus(), STATUS_GRAYING)
                || !validGrayRule(rule)) {
            throw failure(errorCode, dependency, requestedEnvironment, errorMessage);
        }
        if (rule.getPercentage() == FULL_PERCENTAGE) {
            return new SelectedPointer(candidatePointer(state, candidate), true,
                    GrayRouteReason.FULL_PERCENTAGE);
        }
        if (validUserId(userId) && rule.getUserIdWhitelist().contains(userId)) {
            return new SelectedPointer(candidatePointer(state, candidate), true,
                    GrayRouteReason.WHITELIST);
        }
        if (!validUserId(userId)) {
            log.info("灰度资产解析缺少可信userId，回到稳定版本, assetType:{}, assetKey:{}, environment:{}",
                    dependency.getAssetType(), dependency.getAssetKey(), requestedEnvironment);
            return new SelectedPointer(stablePointer(state), false, GrayRouteReason.MISSING_USER_ID);
        }
        boolean candidateMatched = Math.floorMod(userId, USER_BUCKET_COUNT) < rule.getPercentage();
        return candidateMatched
                ? new SelectedPointer(candidatePointer(state, candidate), true, GrayRouteReason.PERCENTAGE)
                : new SelectedPointer(stablePointer(state), false, GrayRouteReason.STABLE_BUCKET);
    }

    private boolean validGrayRule(GrayReleaseRule rule) {
        if (rule == null || rule.getPercentage() == null
                || rule.getPercentage() < MIN_PERCENTAGE
                || rule.getPercentage() > FULL_PERCENTAGE
                || rule.getUserIdWhitelist() == null) {
            return false;
        }
        return rule.getUserIdWhitelist().stream().allMatch(this::validUserId)
                && rule.getUserIdWhitelist().stream().distinct().count()
                == rule.getUserIdWhitelist().size();
    }

    private boolean validUserId(Long userId) {
        return userId != null;
    }

    private EnvironmentState stablePointer(EnvironmentState state) {
        return new EnvironmentState()
                .setEnvironment(state.getEnvironment())
                .setSourceType(state.getSourceType())
                .setSourceId(state.getSourceId())
                .setVersion(state.getVersion())
                .setDigest(state.getDigest())
                .setDeploymentId(state.getDeploymentId())
                .setUpdateTime(state.getUpdateTime());
    }

    private EnvironmentState candidatePointer(EnvironmentState state, ReleasePointer candidate) {
        return new EnvironmentState()
                .setEnvironment(state.getEnvironment())
                .setSourceType(candidate.getSourceType())
                .setSourceId(candidate.getSourceId())
                .setVersion(candidate.getVersion())
                .setDigest(candidate.getDigest())
                .setDeploymentId(candidate.getDeploymentId())
                .setUpdateTime(candidate.getUpdateTime());
    }

    private boolean validPointer(EnvironmentState pointer, ReleaseEnvironment environment,
            ReleasedAssetSourceType sourceType) {
        return pointer != null
                && StringUtils.equals(pointer.getEnvironment(), environment.name())
                && StringUtils.equals(pointer.getSourceType(), sourceType.name())
                && StringUtils.isNotBlank(pointer.getSourceId())
                && pointer.getVersion() != null
                && StringUtils.isNotBlank(pointer.getDigest());
    }

    private boolean validSnapshot(AssetSnapshot snapshot, String assetKey, ReleaseAssetType releaseAssetType,
            String sourceDigest) {
        return snapshot != null
                && StringUtils.equals(snapshot.getAssetType(), releaseAssetType.name())
                && StringUtils.equals(snapshot.getAssetKey(), assetKey)
                && StringUtils.isNotBlank(snapshot.getPayloadJson())
                && StringUtils.equals(snapshot.getDigest(), sourceDigest);
    }

    private ResolvedReleasedAsset resolved(AssetDependencyReference dependency,
            ReleaseEnvironment requestedEnvironment, ReleaseEnvironment resolvedEnvironment,
            ReleasedAssetSourceType sourceType, String sourceId, Integer version, AssetSnapshot snapshot) {
        return new ResolvedReleasedAsset()
                .setAssetType(dependency.getAssetType())
                .setAssetKey(dependency.getAssetKey())
                .setRequestedEnvironment(requestedEnvironment)
                .setResolvedEnvironment(resolvedEnvironment)
                .setSourceType(sourceType)
                .setSourceId(sourceId)
                .setVersion(version)
                .setDigest(snapshot.getDigest())
                .setArtifactRef(snapshot.getArtifactRef())
                .setPayloadJson(snapshot.getPayloadJson())
                .setSummary(snapshot.getSummary() == null
                        ? new LinkedHashMap<>() : new LinkedHashMap<>(snapshot.getSummary()));
    }

    private void verifyEnabled(AssetDependencyAdapter adapter, ResolvedReleasedAsset resolvedAsset,
            AssetDependencyReference dependency, ReleaseEnvironment requestedEnvironment) {
        try {
            if (!adapter.isEnabled(resolvedAsset)) {
                throw failure(AssetDependencyErrorCode.ASSET_DISABLED, dependency,
                        requestedEnvironment, MESSAGE_ASSET_DISABLED);
            }
        } catch (AssetDependencyResolutionException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            AssetDependencyErrorCode errorCode = resolvedAsset.getResolvedEnvironment()
                    == ReleaseEnvironment.PRT
                    ? AssetDependencyErrorCode.PREPROD_POINTER_INVALID
                    : AssetDependencyErrorCode.ONLINE_POINTER_INVALID;
            log.warn("领域Adapter校验不可变快照启用状态失败, assetType:{}, assetKey:{}, "
                            + "requestedEnvironment:{}, resolvedEnvironment:{}, errorType:{}",
                    dependency.getAssetType(), dependency.getAssetKey(), requestedEnvironment,
                    resolvedAsset.getResolvedEnvironment(), exception.getClass().getSimpleName());
            throw failure(errorCode, dependency, requestedEnvironment,
                    resolvedAsset.getResolvedEnvironment() == ReleaseEnvironment.PRT
                            ? MESSAGE_PREPROD_POINTER_INVALID : MESSAGE_ONLINE_POINTER_INVALID);
        }
    }

    private AssetDependencyResolutionException failure(AssetDependencyErrorCode errorCode,
            AssetDependencyReference dependency, ReleaseEnvironment requestedEnvironment, String message) {
        AssetDependencyType assetType = dependency == null ? null : dependency.getAssetType();
        String assetKey = dependency == null ? null : dependency.getAssetKey();
        log.warn("环境资产解析失败, errorCode:{}, assetType:{}, assetKey:{}, requestedEnvironment:{}",
                errorCode, assetType, assetKey, requestedEnvironment);
        return new AssetDependencyResolutionException(errorCode, assetType, assetKey,
                requestedEnvironment, message);
    }

    private String digestPrefix(String digest) {
        return StringUtils.left(StringUtils.defaultString(digest), DIGEST_LOG_PREFIX_LENGTH);
    }

    /** 一次确定性路由选择，后续校验失败不得切换到另一指针。 */
    private static final class SelectedPointer {
        private final EnvironmentState pointer;
        private final boolean candidate;
        private final GrayRouteReason routeReason;

        private SelectedPointer(EnvironmentState pointer, boolean candidate, GrayRouteReason routeReason) {
            this.pointer = pointer;
            this.candidate = candidate;
            this.routeReason = routeReason;
        }
    }
}
