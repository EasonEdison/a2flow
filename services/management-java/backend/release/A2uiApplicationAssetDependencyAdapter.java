package dev.a2flow.management.release;

import java.util.List;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.release.dependency.AssetDependencyAdapter;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyType;

/**
 * A2UI Application 不可变发布快照的依赖领域 Adapter。
 *
 * <p>共享解析器已经严格校验 Application Build/Version 的 appCode、摘要和不可变 payload；本类只
 * 声明发布聚合类型并拒绝空 payload，不读取当前 Registry，也不回退到 COMPONENT 聚合。
 */
@Component
public class A2uiApplicationAssetDependencyAdapter implements AssetDependencyAdapter {

    @Override
    public AssetDependencyType assetType() {
        return AssetDependencyType.A2UI_APPLICATION;
    }

    @Override
    public ReleaseAssetType releaseAssetType() {
        return ReleaseAssetType.A2UI_APPLICATION;
    }

    @Override
    public boolean isEnabled(ResolvedReleasedAsset resolvedAsset) {
        return resolvedAsset != null && StringUtils.isNotBlank(resolvedAsset.getPayloadJson());
    }

    @Override
    public List<AssetDependencyReference> dependencies(ResolvedReleasedAsset resolvedAsset) {
        return List.of();
    }
}
