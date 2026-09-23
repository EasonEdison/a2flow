package dev.a2flow.management.release.dependency;

import java.util.List;

import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;

/**
 * 领域资产接入环境解析和递归依赖校验的扩展点。
 *
 * <p>实现方负责把依赖类型映射到已有发布聚合、解释不可变 payload 的 enabled 语义并声明直接
 * 下游依赖。共享层只处理指针和图算法，不解析组件、能力或编排字段。ORCHESTRATION_CONFIG 本期
 * 不注册实现，调用时会按未支持资产类型失败。
 */
public interface AssetDependencyAdapter {

    /** 返回该 Adapter 承接的稳定依赖类型。 */
    AssetDependencyType assetType();

    /** 返回资产在共享发布状态表中的已有聚合类型。 */
    ReleaseAssetType releaseAssetType();

    /** 根据领域快照判断当前不可变发布源是否仍允许被引用。 */
    boolean isEnabled(ResolvedReleasedAsset resolvedAsset);

    /** 从已通过环境解析的领域快照中提取直接下游依赖；无依赖必须返回空列表。 */
    List<AssetDependencyReference> dependencies(ResolvedReleasedAsset resolvedAsset);
}
