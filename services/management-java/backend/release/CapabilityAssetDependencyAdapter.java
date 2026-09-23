package dev.a2flow.management.release;

import java.util.List;

import jakarta.annotation.Resource;

import org.springframework.stereotype.Component;

import dev.a2flow.management.release.dependency.AssetDependencyAdapter;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyType;

/**
 * 业务能力接入共享环境解析和递归依赖校验的领域 Adapter。
 *
 * <p>该 Adapter 只解释能力不可变 payload 的启用状态和包装组件引用。它不会复制包装组件到 Skill
 * componentBindings，也不会自行选择 PRT Build 或 ONLINE Version。
 */
@Component
public class CapabilityAssetDependencyAdapter implements AssetDependencyAdapter {

    @Resource
    private CapabilityReleasePayloadAdapter capabilityReleasePayloadAdapter;

    @Override
    public AssetDependencyType assetType() {
        return AssetDependencyType.CAPABILITY_ACTION;
    }

    @Override
    public ReleaseAssetType releaseAssetType() {
        return ReleaseAssetType.CAPABILITY_ACTION;
    }

    @Override
    public boolean isEnabled(ResolvedReleasedAsset resolvedAsset) {
        return capabilityReleasePayloadAdapter.isEnabled(
                capabilityReleasePayloadAdapter.snapshot(resolvedAsset), resolvedAsset.getAssetKey());
    }

    @Override
    public List<AssetDependencyReference> dependencies(ResolvedReleasedAsset resolvedAsset) {
        return capabilityReleasePayloadAdapter
                .presentationComponentAssetKeys(
                        capabilityReleasePayloadAdapter.snapshot(resolvedAsset), resolvedAsset.getAssetKey())
                .stream()
                .map(assetKey -> new AssetDependencyReference()
                        .setAssetType(AssetDependencyType.COMPONENT_ASSET)
                        .setAssetKey(assetKey))
                .toList();
    }
}
