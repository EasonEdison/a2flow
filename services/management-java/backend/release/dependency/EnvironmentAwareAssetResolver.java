package dev.a2flow.management.release.dependency;

import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetResolutionContext;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;

/**
 * 按可信环境解析稳定资产身份的共享接口。
 *
 * <p>PRT 优先使用合法 Build，仅在 PRT 指针完全不存在时选择 ONLINE Version；ONLINE
 * 只允许 Version。实现不会读取当前草稿、最大版本或损坏指针对应的替代来源。
 */
public interface EnvironmentAwareAssetResolver {

    /** 解析并校验一个稳定依赖资产的不可变发布来源。 */
    default ResolvedReleasedAsset resolve(AssetDependencyReference dependency,
            ReleaseEnvironment requestedEnvironment) {
        return resolve(dependency, new AssetResolutionContext()
                .setRequestedEnvironment(requestedEnvironment));
    }

    /** 使用可信环境和 userId 解析 stable/candidate 不可变来源。 */
    ResolvedReleasedAsset resolve(AssetDependencyReference dependency,
            AssetResolutionContext context);

    /** 使用本次查询已加载的发布聚合解析，仍校验稳定身份与全部环境规则，不重复读取 Repository。 */
    ResolvedReleasedAsset resolveFromState(AssetDependencyReference dependency,
            AssetResolutionContext context, AssetReleaseState state);

}
