package dev.a2flow.management.release;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.access.AssetAction;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseProjection;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.ReleaseModels.EnvironmentState;
import dev.a2flow.management.release.ReleaseModels.ReleaseBuild;
import dev.a2flow.management.release.ReleaseModels.ReleaseChange;
import dev.a2flow.management.storage.db.repository.AssetReleaseStateRepository;

/**
 * SkillFactory 共享发布环境指针只读查询服务。
 *
 * <p>上游是只需要 PRT/ONLINE 指针的资产列表，下游是 publish-center-common-v2 共享发布状态。
 * 本服务执行稳定资产 VIEW 鉴权，只返回已经存在的环境状态；不读取领域草稿、不编译当前快照、
 * 不执行递归依赖门禁，也不提供草稿或 latest fallback。
 */
@Service
public class AssetReleasePointerQueryService {

    private static final String STATUS_ACTIVE = "ACTIVE";
    private static final String STATUS_UNPUBLISHED = "UNPUBLISHED";
    private static final String STATUS_VERSIONED = "VERSIONED";

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private AssetReleaseStateRepository assetReleaseStateRepository;

    /** 查询资产当前真实存在的 PRT/ONLINE 环境指针。 */
    public Map<String, EnvironmentState> environmentPointers(
            String userName, ReleaseAssetType assetType, String assetKey) {
        return projection(userName, assetType, assetKey).getEnvironmentPointers();
    }

    /**
     * 查询资产当前轻量发布投影。
     *
     * <p>status 只从共享发布聚合的 ACTIVE Change、环境指针、Build 或 Version 事实投影；空聚合明确
     * 返回 UNPUBLISHED。该方法不读取领域草稿，不把 latest 内容作为发布事实，也不持久化投影结果。
     */
    public AssetReleaseProjection projection(
            String userName, ReleaseAssetType assetType, String assetKey) {
        assetAuthorizationService.requirePermission(userName, assetType, assetKey, AssetAction.VIEW);
        AssetReleaseState state = assetReleaseStateRepository.find(assetType, assetKey);
        Map<String, EnvironmentState> result = new LinkedHashMap<>();
        if (state.getEnvironments() != null) {
            copyPointer(state, result, ReleaseEnvironment.PRT);
            copyPointer(state, result, ReleaseEnvironment.ONLINE);
        }
        return new AssetReleaseProjection()
                .setStatus(projectStatus(state, result))
                .setEnvironmentPointers(result);
    }

    private void copyPointer(AssetReleaseState state, Map<String, EnvironmentState> result,
            ReleaseEnvironment environment) {
        EnvironmentState pointer = state.getEnvironments().get(environment.name());
        if (pointer != null) {
            result.put(environment.name(), pointer);
        }
    }

    /**
     * 按 ACTIVE Change、ONLINE/PRT 指针、最新 Build、Version、历史 Change 的优先级投影列表状态。
     * 只有 revision=0 的空聚合或确实没有任何公共发布事实时返回 UNPUBLISHED；不读取领域草稿，
     * 不把 current/latest 内容作为发布状态 fallback。
     */
    private String projectStatus(AssetReleaseState state, Map<String, EnvironmentState> pointers) {
        ReleaseChange activeChange = state.getActiveChange();
        if (activeChange != null && StringUtils.equals(activeChange.getStatus(), STATUS_ACTIVE)) {
            return activeChange.getStatus();
        }
        if (pointers.containsKey(ReleaseEnvironment.ONLINE.name())) {
            return ReleaseEnvironment.ONLINE.name();
        }
        if (pointers.containsKey(ReleaseEnvironment.PRT.name())) {
            return ReleaseEnvironment.PRT.name();
        }
        List<ReleaseBuild> builds = state.getBuilds();
        if (builds != null) {
            for (int index = builds.size() - 1; index >= 0; index--) {
                String buildStatus = builds.get(index).getStatus();
                if (StringUtils.isNotBlank(buildStatus)) {
                    return buildStatus;
                }
            }
        }
        if (state.getVersions() != null && !state.getVersions().isEmpty()) {
            return STATUS_VERSIONED;
        }
        if (activeChange != null && StringUtils.isNotBlank(activeChange.getStatus())) {
            return activeChange.getStatus();
        }
        return STATUS_UNPUBLISHED;
    }
}
