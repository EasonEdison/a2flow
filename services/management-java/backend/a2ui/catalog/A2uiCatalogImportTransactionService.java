package dev.a2flow.management.a2ui.catalog;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import org.springframework.transaction.annotation.Transactional;
import dev.a2flow.management.a2ui.catalog
        .A2uiKuaishouCatalogImporter.KuaishouCatalogSnapshot;
import dev.a2flow.management.a2ui.catalog
        .A2uiOfficialBasicCatalogImporter.OfficialBasicCatalogSnapshot;
import dev.a2flow.management.a2ui.registry
        .A2uiComponentOriginType;
import dev.a2flow.management.a2ui.registry
        .A2uiRegistryValidationException;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.storage.db.mapper
        .SkillFactoryMapperConstants;
import dev.a2flow.management.storage.db.repository
        .SkillFactoryComponentAssetRepository;
import dev.a2flow.management.storage.db.repository
        .SkillFactoryComponentAssetRepository.ComponentAssetQuery;

import lombok.extern.slf4j.Slf4j;

/**
 * A2UI Catalog 受控导入的短数据库事务服务。
 *
 * <p>上游只传入已经完成网络与结构校验、计算原始摘要的内存快照；本类复核摘要元数据一致性，
 * 下游通过共享 Repository 原子更新 atom
 * 与 Catalog 当前态。快手 managed 导入会使遗留 Official 当前行退出消费；Official 固定导入只接受
 * 服务内锁定快照。本类不访问网络、不发布 shared release、不删除不可变历史，也不把 Official 数据
 * 作为失败时的 fallback。
 */
@Service
@Slf4j
public class A2uiCatalogImportTransactionService {

    private static final String ASSET_TYPE_CATALOG = "A2UI_CATALOG";
    private static final String ASSET_TYPE_ATOM = "A2UI_ATOM";
    private static final String FIELD_CATALOG_SOURCE_TYPE = "catalogSourceType";
    private static final String FIELD_COMPONENT_ORIGIN_TYPE = "componentOriginType";
    private static final String FIELD_RAW_DIGEST = "rawDigest";
    private static final String RAW_DIGEST_PATTERN = "[0-9a-f]{64}";
    private static final String ERROR_SNAPSHOT_INVALID = "A2UI_CATALOG_IMPORT_SNAPSHOT_INVALID";
    private static final String ERROR_IMPORT_CONFLICT = "A2UI_CATALOG_IMPORT_CONFLICT";
    private static final int OFFICIAL_COMPONENT_COUNT = 18;

    @Resource
    private SkillFactoryComponentAssetRepository assetRepository;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    /**
     * 在 sellerDataManager 短事务中一次提交完整快照；任一写入异常都回滚，不出现半导入 current source。
     */
    @Transactional(rollbackFor = Exception.class)
    public ComponentAsset importSnapshot(KuaishouCatalogSnapshot snapshot, String operator) {
        validateSnapshot(snapshot);
        for (ComponentAsset atom : snapshot.getAtomAssets()) {
            upsertAtom(atom, operator);
        }
        ComponentAsset catalog = upsertCatalog(snapshot.getCatalogAsset(), operator);
        retireOfficialCurrentRows(operator);
        log.info("快手A2UI Catalog数据库短事务完成, catalogId:{}, atomCount:{}, rawDigest:{}, "
                        + "operator:{}",
                catalog.getComponentName(), snapshot.getAtomAssets().size(),
                snapshot.getRawDigest(), operator);
        return catalog;
    }

    /**
     * 原子写入服务端锁定并验签过的 Official Basic Catalog；不接受客户端 schema。
     */
    @Transactional(rollbackFor = Exception.class)
    public ComponentAsset importOfficialSnapshot(
            OfficialBasicCatalogSnapshot snapshot, String operator) {
        validateOfficialSnapshot(snapshot);
        for (ComponentAsset atom : snapshot.getAtomAssets()) {
            upsertOfficialAtom(atom, operator);
        }
        ComponentAsset catalog = upsertOfficialCatalog(snapshot.getCatalogAsset(), operator);
        log.info("Google A2UI Official Basic Catalog数据库短事务完成, catalogId:{}, "
                        + "sourceCommit:{}, atomCount:{}, operator:{}",
                catalog.getComponentName(), A2uiOfficialBasicCatalogImporter.SOURCE_COMMIT,
                snapshot.getAtomAssets().size(), operator);
        return catalog;
    }

    private void validateOfficialSnapshot(OfficialBasicCatalogSnapshot snapshot) {
        if (snapshot == null || snapshot.getCatalogAsset() == null
                || snapshot.getAtomAssets().size() != OFFICIAL_COMPONENT_COUNT
                || !A2uiOfficialBasicCatalogImporter.CATALOG_ID.equals(
                snapshot.getCatalogAsset().getComponentName())) {
            throw new A2uiRegistryValidationException(ERROR_SNAPSHOT_INVALID);
        }
        Map<String, Object> catalogSource = source(snapshot.getCatalogAsset());
        if (!A2uiCatalogSourceType.A2UI_OFFICIAL.name().equals(
                catalogSource.get(FIELD_CATALOG_SOURCE_TYPE))
                || !A2uiOfficialBasicCatalogImporter.SOURCE_COMMIT.equals(
                catalogSource.get("sourceCommit"))
                || !("sha256:" + A2uiOfficialBasicCatalogImporter.CATALOG_DIGEST).equals(
                catalogSource.get("catalogDigest"))) {
            throw new A2uiRegistryValidationException(ERROR_SNAPSHOT_INVALID);
        }
        Set<String> identities = new LinkedHashSet<>();
        for (ComponentAsset atom : snapshot.getAtomAssets()) {
            Map<String, Object> contract = atom == null ? null : atom.getA2uiContract();
            if (atom == null || contract == null || !identities.add(atom.getComponentName())
                    || !A2uiComponentOriginType.A2UI_OFFICIAL.name().equals(
                    contract.get(FIELD_COMPONENT_ORIGIN_TYPE))
                    || !A2uiOfficialBasicCatalogImporter.CATALOG_ID.equals(
                    contract.get("officialCatalogId"))
                    || !A2uiOfficialBasicCatalogImporter.SOURCE_COMMIT.equals(
                    contract.get("officialSourceCommit"))) {
                throw new A2uiRegistryValidationException(ERROR_SNAPSHOT_INVALID);
            }
        }
    }

    private void upsertOfficialAtom(ComponentAsset next, String operator) {
        ComponentAsset current = assetRepository.findByAssetTypeAndName(
                ASSET_TYPE_ATOM, next.getComponentName());
        if (current == null) {
            ComponentAsset saved = assetRepository.save(next);
            initializeOwner(operator, ReleaseAssetType.A2UI_ATOM, saved.getComponentName());
            return;
        }
        Map<String, Object> contract = current.getA2uiContract();
        if (contract == null || !A2uiComponentOriginType.A2UI_OFFICIAL.name().equals(
                contract.get(FIELD_COMPONENT_ORIGIN_TYPE))) {
            throw new A2uiRegistryValidationException(ERROR_IMPORT_CONFLICT);
        }
        assetRepository.update(next.setId(current.getId()));
    }

    private ComponentAsset upsertOfficialCatalog(ComponentAsset next, String operator) {
        ComponentAsset current = assetRepository.findByAssetTypeAndName(
                ASSET_TYPE_CATALOG, next.getComponentName());
        if (current == null) {
            ComponentAsset saved = assetRepository.save(next);
            initializeOwner(operator, ReleaseAssetType.A2UI_CATALOG, saved.getComponentName());
            return saved;
        }
        if (sourceType(current) != A2uiCatalogSourceType.A2UI_OFFICIAL) {
            throw new A2uiRegistryValidationException(ERROR_IMPORT_CONFLICT);
        }
        return assetRepository.update(next.setId(current.getId()));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> source(ComponentAsset asset) {
        Object value = asset == null || StringUtils.isBlank(asset.getRuntimeConfigJson())
                ? null : JsonSupport.fromJSON(asset.getRuntimeConfigJson(), Object.class);
        if (!(value instanceof Map)) {
            throw new A2uiRegistryValidationException(ERROR_SNAPSHOT_INVALID);
        }
        return (Map<String, Object>) value;
    }

    private void validateSnapshot(KuaishouCatalogSnapshot snapshot) {
        if (snapshot == null || snapshot.getCatalogAsset() == null
                || snapshot.getAtomAssets().size() != A2uiKuaishouCatalogImporter.COMPONENT_TYPES.size()
                || !A2uiKuaishouCatalogImporter.CATALOG_ID.equals(
                snapshot.getCatalogAsset().getComponentName())
                || snapshot.getFunctionCount() != A2uiKuaishouCatalogImporter.FUNCTION_CODES.size()
                || StringUtils.isBlank(snapshot.getRawDigest())
                || !snapshot.getRawDigest().matches(RAW_DIGEST_PATTERN)) {
            throw new A2uiRegistryValidationException(ERROR_SNAPSHOT_INVALID);
        }
        // 摘要由导入器根据实际字节生成，只校验快照一致性，不绑定某一份历史文件。
        Object source = JsonSupport.fromJSON(
                snapshot.getCatalogAsset().getRuntimeConfigJson(), Object.class);
        if (!(source instanceof Map)
                || !snapshot.getRawDigest().equals(((Map<?, ?>) source).get(FIELD_RAW_DIGEST))) {
            throw new A2uiRegistryValidationException(ERROR_SNAPSHOT_INVALID);
        }
    }

    private void upsertAtom(ComponentAsset next, String operator) {
        ComponentAsset current = assetRepository.findByAssetTypeAndName(
                ASSET_TYPE_ATOM, next.getComponentName());
        if (current == null) {
            ComponentAsset saved = assetRepository.save(next);
            initializeOwner(operator, ReleaseAssetType.A2UI_ATOM, saved.getComponentName());
            return;
        }
        Map<String, Object> contract = current.getA2uiContract();
        String origin = contract == null ? null
                : String.valueOf(contract.get(FIELD_COMPONENT_ORIGIN_TYPE));
        if (!StringUtils.equalsAny(origin, A2uiComponentOriginType.A2UI_OFFICIAL.name(),
                A2uiComponentOriginType.PLATFORM_CUSTOM.name())) {
            throw new A2uiRegistryValidationException(ERROR_IMPORT_CONFLICT);
        }
        assetRepository.update(next.setId(current.getId()));
    }

    private ComponentAsset upsertCatalog(ComponentAsset next, String operator) {
        ComponentAsset current = assetRepository.findByAssetTypeAndName(
                ASSET_TYPE_CATALOG, next.getComponentName());
        if (current == null) {
            ComponentAsset saved = assetRepository.save(next);
            initializeOwner(operator, ReleaseAssetType.A2UI_CATALOG, saved.getComponentName());
            return saved;
        }
        A2uiCatalogSourceType currentSource = sourceType(current);
        if (currentSource != A2uiCatalogSourceType.PLATFORM_MANAGED
                && currentSource != A2uiCatalogSourceType.A2UI_OFFICIAL) {
            throw new A2uiRegistryValidationException(ERROR_IMPORT_CONFLICT);
        }
        return assetRepository.update(next.setId(current.getId()));
    }

    private void retireOfficialCurrentRows(String operator) {
        List<ComponentAsset> atoms = assetRepository.list(
                new ComponentAssetQuery().setAssetType(ASSET_TYPE_ATOM), false);
        for (ComponentAsset atom : atoms) {
            Map<String, Object> contract = atom == null ? null : atom.getA2uiContract();
            if (contract != null && A2uiComponentOriginType.A2UI_OFFICIAL.name().equals(
                    contract.get(FIELD_COMPONENT_ORIGIN_TYPE))) {
                assetRepository.offline(atom.getId(), operator);
            }
        }
        List<ComponentAsset> catalogs = assetRepository.list(
                new ComponentAssetQuery().setAssetType(ASSET_TYPE_CATALOG), false);
        for (ComponentAsset catalog : catalogs) {
            if (catalog != null && sourceType(catalog) == A2uiCatalogSourceType.A2UI_OFFICIAL) {
                assetRepository.offline(catalog.getId(), operator);
            }
        }
    }

    @SuppressWarnings("unchecked")
    private A2uiCatalogSourceType sourceType(ComponentAsset catalog) {
        if (catalog == null || StringUtils.isBlank(catalog.getRuntimeConfigJson())) {
            throw new A2uiRegistryValidationException(ERROR_IMPORT_CONFLICT);
        }
        try {
            Object value = JsonSupport.fromJSON(catalog.getRuntimeConfigJson(), Object.class);
            if (!(value instanceof Map)) {
                throw new A2uiRegistryValidationException(ERROR_IMPORT_CONFLICT);
            }
            Object source = ((Map<String, Object>) value).get(FIELD_CATALOG_SOURCE_TYPE);
            return A2uiCatalogSourceType.parse(source == null ? null : String.valueOf(source));
        } catch (A2uiRegistryValidationException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new A2uiRegistryValidationException(ERROR_IMPORT_CONFLICT);
        }
    }

    private void initializeOwner(String operator, ReleaseAssetType assetType, String assetKey) {
        if (assetAuthorizationService != null) {
            assetAuthorizationService.initializeOwners(operator, assetType, assetKey, null);
        }
    }
}
