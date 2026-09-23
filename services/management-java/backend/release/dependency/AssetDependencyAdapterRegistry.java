package dev.a2flow.management.release.dependency;

import java.util.EnumMap;
import java.util.Map;
import java.util.Optional;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Component;

/**
 * 环境资产依赖 Adapter 注册表。
 *
 * <p>Spring 启动时收集各领域提供的 Adapter，同一依赖类型只能有一个实现。注册表不创建默认
 * Adapter，因此未激活的 ORCHESTRATION_CONFIG 会保持显式不可用，不会静默使用其他资产逻辑。
 */
@Component
public class AssetDependencyAdapterRegistry {

    private static final String ERROR_DUPLICATE_ADAPTER = "重复的资产依赖Adapter: ";

    private final Map<AssetDependencyType, AssetDependencyAdapter> adapters =
            new EnumMap<>(AssetDependencyType.class);

    public AssetDependencyAdapterRegistry(ObjectProvider<AssetDependencyAdapter> adapterProvider) {
        adapterProvider.orderedStream().forEach(this::register);
    }

    /** 查询已激活的领域 Adapter；未注册类型返回空，不创建兜底实现。 */
    public Optional<AssetDependencyAdapter> find(AssetDependencyType assetType) {
        return Optional.ofNullable(adapters.get(assetType));
    }

    private void register(AssetDependencyAdapter adapter) {
        AssetDependencyAdapter previous = adapters.putIfAbsent(adapter.assetType(), adapter);
        if (previous != null) {
            throw new IllegalStateException(ERROR_DUPLICATE_ADAPTER + adapter.assetType());
        }
    }
}
