package dev.a2flow.management.release;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.ReleaseModels.EnvironmentState;
import dev.a2flow.management.release.ReleaseModels.PublishedAssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.ReleaseBuild;
import dev.a2flow.management.release.ReleaseModels.ReleaseVersion;
import dev.a2flow.management.storage.db.repository.AssetReleaseStateRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 当前正式资产快照查询服务。
 *
 * <p>该服务只认调用方显式指定的共享发布环境指针，并返回指针命中的唯一不可变正式版本快照。
 * 草稿、其他环境、未成功发布的版本和状态不一致的聚合都不会被读取。
 */
@Service
@Slf4j
public class PublishedAssetQueryService {

    private static final String ERROR_PUBLISHED_ASSET_NOT_FOUND = "published asset not found";
    private static final String SOURCE_BUILD = "BUILD";

    @Resource
    private AssetReleaseStateRepository assetReleaseStateRepository;

    /** 查询某类资产当前 ONLINE 正式版本列表。 */
    public List<PublishedAssetSnapshot> listOnline(ReleaseAssetType assetType) {
        return listPublished(assetType, ReleaseEnvironment.ONLINE);
    }

    /** 查询某类资产指定环境的正式版本列表。 */
    public List<PublishedAssetSnapshot> listPublished(
            ReleaseAssetType assetType, ReleaseEnvironment environment) {
        List<PublishedAssetSnapshot> result = new ArrayList<>();
        assetReleaseStateRepository.scanByAssetType(assetType,
                state -> resolve(state, environment).ifPresent(result::add));
        log.info("SkillFactory查询指定环境正式资产完成, assetType:{}, environment:{}, count:{}",
                assetType, environment, result.size());
        return List.copyOf(result);
    }

    /** 按资产稳定 ID 读取当前 ONLINE 正式版本，不允许回退到当前草稿。 */
    public PublishedAssetSnapshot requireOnline(ReleaseAssetType assetType, String assetKey) {
        return requirePublished(assetType, assetKey, ReleaseEnvironment.ONLINE);
    }

    /** 按资产稳定 ID 和指定环境读取正式版本，不允许回退到其他环境或当前草稿。 */
    public PublishedAssetSnapshot requirePublished(ReleaseAssetType assetType, String assetKey,
            ReleaseEnvironment environment) {
        AssetReleaseState state = assetReleaseStateRepository.find(assetType, assetKey);
        return resolve(state, environment).orElseThrow(() -> {
            log.warn("SkillFactory正式资产不存在或环境指针无效, assetType:{}, assetKey:{}, environment:{}",
                    assetType, assetKey, environment);
            return new IllegalArgumentException(ERROR_PUBLISHED_ASSET_NOT_FOUND);
        });
    }

    /** 从同一份发布聚合解析各环境指针，避免列表投影为每个环境重复加载历史快照。 */
    public Map<ReleaseEnvironment, PublishedAssetSnapshot> publishedEnvironments(
            ReleaseAssetType assetType, String assetKey) {
        AssetReleaseState state = assetReleaseStateRepository.find(assetType, assetKey);
        Map<ReleaseEnvironment, PublishedAssetSnapshot> result = new EnumMap<>(ReleaseEnvironment.class);
        for (ReleaseEnvironment environment : ReleaseEnvironment.values()) {
            resolve(state, environment).ifPresent(snapshot -> result.put(environment, snapshot));
        }
        return result;
    }

    private Optional<PublishedAssetSnapshot> resolve(
            AssetReleaseState state, ReleaseEnvironment environment) {
        if (state == null || environment == null
                || state.getEnvironments() == null || state.getVersions() == null) {
            return Optional.empty();
        }
        EnvironmentState environmentState = state.getEnvironments().get(environment.name());
        if (environmentState == null || environmentState.getVersion() == null) {
            return Optional.empty();
        }
        if (StringUtils.equals(SOURCE_BUILD, environmentState.getSourceType())) {
            return resolveBuild(state, environment, environmentState);
        }
        Optional<ReleaseVersion> version = state.getVersions().stream()
                .filter(item -> Objects.equals(item.getVersion(), environmentState.getVersion()))
                .filter(item -> item.getSnapshot() != null)
                .findFirst();
        if (version.isEmpty()) {
            log.warn("SkillFactory环境指针未命中正式版本, assetType:{}, assetKey:{}, environment:{}, version:{}",
                    state.getAssetType(), state.getAssetKey(), environment, environmentState.getVersion());
            return Optional.empty();
        }
        ReleaseVersion formalVersion = version.get();
        if (StringUtils.isNotBlank(environmentState.getDigest())
                && !StringUtils.equals(environmentState.getDigest(), formalVersion.getSourceDigest())) {
            log.warn("SkillFactory环境摘要与正式版本不一致, assetType:{}, assetKey:{}, environment:{}, version:{}",
                    state.getAssetType(), state.getAssetKey(), environment, environmentState.getVersion());
            return Optional.empty();
        }
        return Optional.of(new PublishedAssetSnapshot()
                .setAssetKey(state.getAssetKey())
                .setVersion(formalVersion.getVersion())
                .setVersionId(formalVersion.getVersionId())
                .setSourceBuildId(formalVersion.getSourceBuildId())
                .setInputDigest(formalVersion.getInputDigest())
                .setSnapshot(formalVersion.getSnapshot()));
    }

    /** PRT 指向不可变 Build 时按 exact buildId 读取，不等待 ONLINE 封板 Version。 */
    private Optional<PublishedAssetSnapshot> resolveBuild(
            AssetReleaseState state, ReleaseEnvironment environment,
            EnvironmentState environmentState) {
        Optional<ReleaseBuild> build = state.getBuilds().stream()
                .filter(item -> StringUtils.equals(
                        item.getBuildId(), environmentState.getSourceId()))
                .filter(item -> Objects.equals(
                        item.getTargetVersion(), environmentState.getVersion()))
                .filter(item -> item.getSnapshot() != null)
                .findFirst();
        if (build.isEmpty()) {
            log.warn("SkillFactory预发指针未命中不可变Build, assetType:{}, assetKey:{}, "
                            + "environment:{}, buildId:{}, version:{}",
                    state.getAssetType(), state.getAssetKey(), environment,
                    environmentState.getSourceId(), environmentState.getVersion());
            return Optional.empty();
        }
        ReleaseBuild frozenBuild = build.get();
        if (StringUtils.isNotBlank(environmentState.getDigest())
                && !StringUtils.equals(
                        environmentState.getDigest(), frozenBuild.getSourceDigest())) {
            log.warn("SkillFactory预发指针摘要与不可变Build不一致, assetType:{}, assetKey:{}, "
                            + "environment:{}, buildId:{}",
                    state.getAssetType(), state.getAssetKey(), environment,
                    environmentState.getSourceId());
            return Optional.empty();
        }
        return Optional.of(new PublishedAssetSnapshot()
                .setAssetKey(state.getAssetKey())
                .setVersion(frozenBuild.getTargetVersion())
                .setVersionId(frozenBuild.getBuildId())
                .setSourceBuildId(frozenBuild.getBuildId())
                .setInputDigest(frozenBuild.getInputDigest())
                .setSnapshot(frozenBuild.getSnapshot()));
    }
}
