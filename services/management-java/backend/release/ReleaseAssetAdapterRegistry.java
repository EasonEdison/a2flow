package dev.a2flow.management.release;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

/**
 * 发布资产 Adapter 注册表。
 *
 * <p>Spring 启动时收集所有 {@link ReleaseAssetAdapter}，并保证每个资产类型只能有一个实现。
 * 共享状态机通过注册表路由，不编写 assetType 分支。
 */
@Component
public class ReleaseAssetAdapterRegistry {

    private final Map<ReleaseAssetType, ReleaseAssetAdapter> adapters = new EnumMap<>(ReleaseAssetType.class);

    public ReleaseAssetAdapterRegistry(List<ReleaseAssetAdapter> adapterList) {
        for (ReleaseAssetAdapter adapter : adapterList) {
            ReleaseAssetAdapter previous = adapters.put(adapter.assetType(), adapter);
            if (previous != null) {
                throw new IllegalStateException("duplicate release adapter: " + adapter.assetType());
            }
        }
    }

    /** 查询指定资产类型的唯一 Adapter。 */
    public ReleaseAssetAdapter get(ReleaseAssetType assetType) {
        ReleaseAssetAdapter adapter = adapters.get(assetType);
        if (adapter == null) {
            throw new IllegalArgumentException("release adapter not found: " + assetType);
        }
        return adapter;
    }
}
