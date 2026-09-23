package dev.a2flow.management.release;

import java.util.List;

import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.model.SkillFactoryComponentAsset;
import dev.a2flow.management.release.dependency.AssetDependencyAdapter;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyType;

/**
 * 组件不可变发布快照的依赖领域 Adapter。
 *
 * <p>组件没有下游资产；本类只解释冻结 payload 的 enabled 字段，不读取当前 Registry，
 * 不修改组件资产，也不参与组件运行态模板或 bundle 选择。
 */
@Component
public class ComponentAssetDependencyAdapter implements AssetDependencyAdapter {

    @Override
    public AssetDependencyType assetType() {
        return AssetDependencyType.COMPONENT_ASSET;
    }

    @Override
    public ReleaseAssetType releaseAssetType() {
        return ReleaseAssetType.COMPONENT;
    }

    @Override
    public boolean isEnabled(ResolvedReleasedAsset resolvedAsset) {
        SkillFactoryComponentAsset asset = JsonSupport.fromJSON(
                resolvedAsset.getPayloadJson(), SkillFactoryComponentAsset.class);
        return asset != null && Boolean.TRUE.equals(asset.getEnabled());
    }

    @Override
    public List<AssetDependencyReference> dependencies(ResolvedReleasedAsset resolvedAsset) {
        return List.of();
    }
}
