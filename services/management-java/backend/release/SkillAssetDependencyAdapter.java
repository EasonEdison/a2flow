package dev.a2flow.management.release;

import java.util.List;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.dependency.AssetDependencyAdapter;
import dev.a2flow.management.release.dependency.AssetDependencyErrorCode;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyResolutionException;
import dev.a2flow.management.release.dependency.AssetDependencyResolutionException.ResolutionCause;
import dev.a2flow.management.release.dependency.AssetDependencyType;

/**
 * Skill 不可变发布快照接入公共环境解析和递归依赖校验的领域 Adapter。
 *
 * <p>上游公共解析器负责从 PRT Build 或 ONLINE Version 取得冻结 Skill 快照，本类只校验快照
 * 身份并复用 {@link SkillReleaseBindingSnapshotReader} 展开 Capability/Component 直接依赖。它不读取
 * Skill 草稿或 latest workspace，不选择环境指针，也不复制 Skill 私有发布状态。
 */
@Component
public class SkillAssetDependencyAdapter implements AssetDependencyAdapter {

    private static final String ERROR_SKILL_SNAPSHOT_INVALID = "Skill冻结发布快照身份非法";
    private static final String ERROR_SKILL_PAYLOAD_INVALID = "Skill冻结发布正文非法";
    private static final String PATH_SKILL_SNAPSHOT = "snapshot";
    private static final String PATH_SKILL_PAYLOAD = "snapshot.payload";

    @Resource
    private SkillReleaseBindingSnapshotReader bindingSnapshotReader;

    @Override
    public AssetDependencyType assetType() {
        return AssetDependencyType.SKILL;
    }

    @Override
    public ReleaseAssetType releaseAssetType() {
        return ReleaseAssetType.SKILL;
    }

    /** 仅接受公共解析器返回的完整 Skill 冻结发布事实。 */
    @Override
    public boolean isEnabled(ResolvedReleasedAsset resolvedAsset) {
        requireValidSnapshot(resolvedAsset);
        return true;
    }

    /** 从冻结 Skill payload 展开稳定的 Capability/Component 直接依赖。 */
    @Override
    public List<AssetDependencyReference> dependencies(ResolvedReleasedAsset resolvedAsset) {
        AssetSnapshot snapshot = snapshot(resolvedAsset);
        try {
            return bindingSnapshotReader.readDirectDependencies(snapshot).stream()
                    .map(dependency -> new AssetDependencyReference()
                            .setAssetType(dependency.getAssetType())
                            .setAssetKey(dependency.getAssetKey()))
                    .toList();
        } catch (AssetDependencyResolutionException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw payloadFailure(resolvedAsset, exception);
        }
    }

    private AssetSnapshot snapshot(ResolvedReleasedAsset resolvedAsset) {
        requireValidSnapshot(resolvedAsset);
        return new AssetSnapshot()
                .setAssetType(ReleaseAssetType.SKILL.name())
                .setAssetKey(resolvedAsset.getAssetKey())
                .setDigest(resolvedAsset.getDigest())
                .setArtifactRef(resolvedAsset.getArtifactRef())
                .setSummary(resolvedAsset.getSummary())
                .setPayloadJson(resolvedAsset.getPayloadJson());
    }

    private void requireValidSnapshot(ResolvedReleasedAsset resolvedAsset) {
        if (resolvedAsset == null
                || resolvedAsset.getAssetType() != AssetDependencyType.SKILL
                || StringUtils.isBlank(resolvedAsset.getAssetKey())
                || StringUtils.isBlank(resolvedAsset.getDigest())
                || StringUtils.isBlank(resolvedAsset.getPayloadJson())) {
            throw new AssetDependencyResolutionException(
                    AssetDependencyErrorCode.ASSET_REFERENCE_INVALID,
                    AssetDependencyType.SKILL,
                    resolvedAsset == null ? null : resolvedAsset.getAssetKey(),
                    null,
                    ERROR_SKILL_SNAPSHOT_INVALID,
                    new ResolutionCause("SKILL_FROZEN_SNAPSHOT_INVALID", PATH_SKILL_SNAPSHOT),
                    null);
        }
    }

    private AssetDependencyResolutionException payloadFailure(
            ResolvedReleasedAsset resolvedAsset, RuntimeException cause) {
        return new AssetDependencyResolutionException(
                AssetDependencyErrorCode.DEPENDENCY_EXPANSION_FAILED,
                AssetDependencyType.SKILL,
                resolvedAsset == null ? null : resolvedAsset.getAssetKey(),
                null,
                ERROR_SKILL_PAYLOAD_INVALID,
                new ResolutionCause("SKILL_FROZEN_PAYLOAD_INVALID", PATH_SKILL_PAYLOAD),
                cause);
    }
}
