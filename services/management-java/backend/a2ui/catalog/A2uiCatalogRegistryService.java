package dev.a2flow.management.a2ui.catalog;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application.A2uiImmutableJsonSupport;
import dev.a2flow.management.a2ui.catalog
        .A2uiKuaishouCatalogImporter.KuaishouCatalogSnapshot;
import dev.a2flow.management.a2ui.catalog
        .A2uiOfficialBasicCatalogImporter.OfficialBasicCatalogSnapshot;
import dev.a2flow.management.a2ui.registry.A2uiRegistryValidationException;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.storage.db.repository
        .SkillFactoryComponentAssetRepository;
import dev.a2flow.management.storage.db.repository
        .SkillFactoryComponentAssetRepository.ComponentAssetQuery;

import lombok.extern.slf4j.Slf4j;

/**
 * A2UI_CATALOG 当前 canonical source 与共享 Registry 的转换服务。
 *
 * <p>上游普通作者态只能创建 PLATFORM_MANAGED source，下游把唯一当前态写入
 * `skill_component_registry.runtime_config_json`。完整快手 Catalog 快照只能由受控导入用例通过 URL
 * 或原始 JSON 构造；Google Official Catalog 只能来自随服务发布的锁定资源，二者都不能通过普通请求
 * 伪造。本服务不发布 Catalog、不写 support evidence，也不按 identity 猜来源。
 */
@Service
@Slf4j
public class A2uiCatalogRegistryService {

    private static final String ASSET_TYPE_A2UI_CATALOG = "A2UI_CATALOG";
    private static final String PROTOCOL_VERSION = "v0.9.1";
    private static final String ERROR_PAYLOAD_REQUIRED = "A2UI_CATALOG_PAYLOAD_REQUIRED";
    private static final String ERROR_REQUIRED_FIELD = "A2UI_CATALOG_REQUIRED_FIELD_MISSING";
    private static final String ERROR_AUTHORITY_FORBIDDEN = "A2UI_CATALOG_AUTHORITY_INPUT_FORBIDDEN";
    private static final String ERROR_PROTOCOL_INVALID = "A2UI_CATALOG_PROTOCOL_INVALID";
    private static final String ERROR_MEMBERSHIP_INVALID = "A2UI_CATALOG_MEMBERSHIP_INVALID";
    private static final String ERROR_SOURCE_INVALID = "A2UI_CATALOG_SOURCE_INVALID";
    private static final String ERROR_ID_INVALID = "A2UI_CATALOG_ID_INVALID";
    private static final String ERROR_NOT_FOUND = "A2UI_CATALOG_NOT_FOUND";
    private static final String ERROR_DUPLICATE = "A2UI_CATALOG_DUPLICATE";
    private static final String ERROR_READ_ONLY = "A2UI_OFFICIAL_CATALOG_RETIRED";
    private static final String ERROR_IMPORT_FORBIDDEN = "A2UI_CATALOG_MANAGED_IMPORT_FORBIDDEN";
    private static final String ERROR_OFFICIAL_IMPORT_FORBIDDEN =
            "A2UI_CATALOG_OFFICIAL_IMPORT_FORBIDDEN";
    private static final String PARAM_KEYWORD = "keyword";
    private static final String PARAM_CATALOG_SOURCE_TYPE = "catalogSourceType";
    private static final String FIELD_FUNCTION_CONTRACT = "functionContract";
    private static final List<String> IMPORT_METADATA_FIELDS = Arrays.asList(
            "sourceUrl", "rawDigest", "functionCodes", "functions", "catalogManifest");
    private static final List<String> AUTHORITY_FIELDS = Arrays.asList(
            "catalogSourceType", "type", "editable", "readOnly", "sourceCommit",
            "catalogDigest", "rulesDigest", "protocolDigests", "frontendSupport",
            "hostProfile", "rendererArtifactDigest", "revision", "release",
            "sourceUrl", "rawDigest", "functionCodes", "functions", "catalogManifest");

    @Resource
    private SkillFactoryComponentAssetRepository assetRepository;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private A2uiKuaishouCatalogImporter kuaishouCatalogImporter;

    @Resource
    private A2uiOfficialBasicCatalogImporter officialBasicCatalogImporter;

    @Resource
    private A2uiCatalogImportTransactionService catalogImportTransactionService;

    private final A2uiCatalogFunctionContractValidator functionContractValidator =
            new A2uiCatalogFunctionContractValidator();

    /**
     * 由平台管理员导入随当前 M 二进制锁定的 Google A2UI Official Basic Catalog。
     *
     * <p>该入口不接收 URL、schema 或 Catalog identity；导入器会复核内置资源的 commit 与摘要，
     * 普通作者态请求无法借此伪造 Official 来源。
     */
    public Map<String, Object> importOfficial(String operator) {
        if (assetAuthorizationService == null || !assetAuthorizationService.isAdmin(operator)) {
            throw new A2uiRegistryValidationException(ERROR_OFFICIAL_IMPORT_FORBIDDEN);
        }
        OfficialBasicCatalogSnapshot snapshot =
                officialBasicCatalogImporter.loadLockedSnapshot(operator);
        functionContractValidator.publishedContract(
                A2uiOfficialBasicCatalogImporter.CATALOG_ID, source(snapshot.getCatalogAsset()));
        ComponentAsset savedCatalog =
                catalogImportTransactionService.importOfficialSnapshot(snapshot, operator);
        Map<String, Object> result = project(savedCatalog);
        result.put("importedAtomCount", snapshot.getAtomAssets().size());
        log.info("Google A2UI Official Basic Catalog 锁定快照导入完成, catalogId:{}, "
                        + "sourceCommit:{}, atomCount:{}, operator:{}",
                savedCatalog.getComponentName(), A2uiOfficialBasicCatalogImporter.SOURCE_COMMIT,
                snapshot.getAtomAssets().size(), operator);
        return result;
    }

    /**
     * 将普通平台管理请求转换成 PLATFORM_MANAGED Catalog 当前行。
     */
    public ComponentAsset toManagedRegistryAsset(Map<String, Object> input, String operator) {
        validateOrdinaryAuthority(input);
        String catalogId = text(input, "catalogId");
        String nameCn = text(input, "nameCn");
        String protocolVersion = text(input, "protocolVersion");
        List<String> componentCodes = componentCodes(input.get("componentCodes"));
        if (StringUtils.isAnyBlank(catalogId, nameCn, protocolVersion)) {
            throw new A2uiRegistryValidationException(ERROR_REQUIRED_FIELD);
        }
        if (!PROTOCOL_VERSION.equals(protocolVersion)) {
            throw new A2uiRegistryValidationException(ERROR_PROTOCOL_INVALID);
        }
        Map<String, Object> source = new LinkedHashMap<>();
        source.put("catalogId", catalogId);
        source.put("nameCn", nameCn);
        source.put("description", text(input, "description"));
        source.put("protocolVersion", PROTOCOL_VERSION);
        source.put("catalogSourceType", A2uiCatalogSourceType.PLATFORM_MANAGED.name());
        source.put("componentCodes", componentCodes);
        if (input.containsKey(FIELD_FUNCTION_CONTRACT)) {
            A2uiCatalogFunctionContractValidator.ValidatedFunctionContract functionContract =
                    functionContractValidator.validateProjectContract(
                            catalogId, input.get(FIELD_FUNCTION_CONTRACT));
            source.put(FIELD_FUNCTION_CONTRACT, functionContract.contract());
            source.put("functionCodes", functionContract.functionCodes());
            source.put("functions", functionContract.functions());
        }
        String canonicalSource = JsonSupport.toJSON(A2uiImmutableJsonSupport.canonicalize(source));
        log.info("A2UI managed Catalog canonical source 已生成, catalogId:{}, componentCount:{}, operator:{}",
                catalogId, componentCodes.size(), operator);
        return new ComponentAsset()
                .setAssetType(ASSET_TYPE_A2UI_CATALOG)
                .setComponentName(catalogId)
                .setComponentNameCn(nameCn)
                .setRuntimeConfigJson(canonicalSource)
                .setEnabled(Boolean.TRUE)
                .setOperator(StringUtils.trimToNull(operator));
    }

    /** 查询同一 A2UI_CATALOG 资产集合，可按服务端 canonical 来源精确过滤。 */
    public List<Map<String, Object>> list(Map<String, String> params) {
        String keyword = params == null ? null : params.get(PARAM_KEYWORD);
        String sourceFilter = params == null ? null : params.get(PARAM_CATALOG_SOURCE_TYPE);
        A2uiCatalogSourceType expected = StringUtils.isBlank(sourceFilter)
                ? null : parseSourceCode(sourceFilter);
        List<ComponentAsset> assets = assetRepository.list(new ComponentAssetQuery()
                .setAssetType(ASSET_TYPE_A2UI_CATALOG)
                .setKeyword(keyword), false);
        List<Map<String, Object>> result = new ArrayList<>();
        if (assets != null) {
            for (ComponentAsset asset : assets) {
                Map<String, Object> projection = project(asset);
                A2uiCatalogSourceType actual = parseSourceCode(
                        String.valueOf(projection.get("catalogSourceType")));
                if (expected == null || expected == actual) {
                    result.add(projection);
                }
            }
        }
        return result;
    }

    /** 按共享 Registry 主键读取 Catalog 服务端投影。 */
    public Map<String, Object> detail(String id) {
        ComponentAsset asset = assetRepository.get(parseId(id));
        if (asset == null || !ASSET_TYPE_A2UI_CATALOG.equals(asset.getAssetType())) {
            throw new A2uiRegistryValidationException(ERROR_NOT_FOUND);
        }
        return project(asset);
    }

    /** 创建普通 PLATFORM_MANAGED Catalog；来源不可由请求指定。 */
    public Map<String, Object> create(String operator, Map<String, Object> input) {
        ComponentAsset next = toManagedRegistryAsset(input, operator);
        if (assetRepository.existsComponentIdentity(null, ASSET_TYPE_A2UI_CATALOG,
                next.getComponentName())) {
            throw new A2uiRegistryValidationException(ERROR_DUPLICATE);
        }
        ComponentAsset saved = assetRepository.save(next);
        initializeOwner(operator, ReleaseAssetType.A2UI_CATALOG, next.getComponentName());
        return project(saved);
    }

    /** 只允许更新 PLATFORM_MANAGED Catalog；Official 当前行只能重新受信导入。 */
    public Map<String, Object> update(String operator, String id, Map<String, Object> input) {
        Long assetId = parseId(id);
        ComponentAsset current = assetRepository.get(assetId);
        if (current == null || !ASSET_TYPE_A2UI_CATALOG.equals(current.getAssetType())) {
            throw new A2uiRegistryValidationException(ERROR_NOT_FOUND);
        }
        if (parseSource(source(current)) == A2uiCatalogSourceType.A2UI_OFFICIAL) {
            throw new A2uiRegistryValidationException(ERROR_READ_ONLY);
        }
        ComponentAsset next = preserveImportMetadata(
                current, toManagedRegistryAsset(input, operator)).setId(assetId);
        if (assetRepository.existsComponentIdentity(assetId, ASSET_TYPE_A2UI_CATALOG,
                next.getComponentName())) {
            throw new A2uiRegistryValidationException(ERROR_DUPLICATE);
        }
        return project(assetRepository.update(next));
    }

    /**
     * 由平台管理员读取并原子导入一份完整快手 Catalog 网络快照。
     *
     * <p>网络读取和完整校验先在事务外完成，只有校验后的内存快照进入数据库短事务。
     */
    public Map<String, Object> importManaged(String operator, String sourceUrl) {
        return importManaged(operator, sourceUrl, null);
    }

    /**
     * 由平台管理员从 URL 或原始 JSON 二选一导入完整快手 Catalog 快照。
     */
    public Map<String, Object> importManaged(String operator, String sourceUrl,
            String catalogJson) {
        if (assetAuthorizationService == null || !assetAuthorizationService.isAdmin(operator)) {
            throw new A2uiRegistryValidationException(ERROR_IMPORT_FORBIDDEN);
        }
        KuaishouCatalogSnapshot snapshot = kuaishouCatalogImporter.loadSnapshot(
                sourceUrl, catalogJson, operator);
        ComponentAsset savedCatalog = catalogImportTransactionService.importSnapshot(snapshot, operator);
        Map<String, Object> result = project(savedCatalog);
        result.put("importedAtomCount", snapshot.getAtomAssets().size());
        result.put("functionCount", snapshot.getFunctionCount());
        result.put("rawDigest", snapshot.getRawDigest());
        log.info("快手A2UI Catalog受信导入完成, catalogId:{}, atomCount:{}, functionCount:{}, "
                        + "rawDigest:{}, operator:{}",
                savedCatalog.getComponentName(), snapshot.getAtomAssets().size(),
                snapshot.getFunctionCount(), snapshot.getRawDigest(), operator);
        return result;
    }

    /**
     * 从 Registry 当前行生成服务端来源和可编辑性投影；非法 source 不返回猜测值。
     */
    public Map<String, Object> project(ComponentAsset asset) {
        Map<String, Object> source = source(asset);
        A2uiCatalogSourceType sourceType = parseSource(source);
        if (!asset.getComponentName().equals(text(source, "catalogId"))
                || !PROTOCOL_VERSION.equals(text(source, "protocolVersion"))) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
        }
        Map<String, Object> result = new LinkedHashMap<>(source);
        result.put("id", asset == null || asset.getId() == null ? null : String.valueOf(asset.getId()));
        result.put("catalogSourceType", sourceType.name());
        result.put("editable", sourceType == A2uiCatalogSourceType.PLATFORM_MANAGED);
        result.put("enabled", asset != null && Boolean.TRUE.equals(asset.getEnabled()));
        result.put("createTime", asset == null ? null : asset.getCreateTime());
        result.put("updateTime", asset == null ? null : asset.getUpdateTime());
        return result;
    }

    private void initializeOwner(String operator, ReleaseAssetType assetType, String assetKey) {
        if (assetAuthorizationService != null) {
            assetAuthorizationService.initializeOwners(operator, assetType, assetKey, null);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> source(ComponentAsset asset) {
        if (asset == null || !ASSET_TYPE_A2UI_CATALOG.equals(asset.getAssetType())
                || StringUtils.isBlank(asset.getRuntimeConfigJson())) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
        }
        Object value = JsonSupport.fromJSON(asset.getRuntimeConfigJson(), Object.class);
        if (!(value instanceof Map)) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
        }
        return (Map<String, Object>) value;
    }

    private A2uiCatalogSourceType parseSource(Map<String, Object> source) {
        try {
            return A2uiCatalogSourceType.parse(text(source, "catalogSourceType"));
        } catch (RuntimeException exception) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
        }
    }

    private A2uiCatalogSourceType parseSourceCode(String sourceType) {
        try {
            return A2uiCatalogSourceType.parse(StringUtils.trim(sourceType));
        } catch (RuntimeException exception) {
            throw new A2uiRegistryValidationException(ERROR_SOURCE_INVALID);
        }
    }

    private void validateOrdinaryAuthority(Map<String, Object> input) {
        if (input == null) {
            throw new A2uiRegistryValidationException(ERROR_PAYLOAD_REQUIRED);
        }
        for (String field : AUTHORITY_FIELDS) {
            if (input.containsKey(field)) {
                throw new A2uiRegistryValidationException(ERROR_AUTHORITY_FORBIDDEN);
            }
        }
    }

    private ComponentAsset preserveImportMetadata(ComponentAsset current, ComponentAsset next) {
        Map<String, Object> currentSource = source(current);
        Map<String, Object> nextSource = source(next);
        if (currentSource.containsKey("sourceUrl") || currentSource.containsKey("rawDigest")
                || currentSource.containsKey("catalogManifest")) {
            for (String field : IMPORT_METADATA_FIELDS) {
                if (currentSource.containsKey(field)) {
                    nextSource.put(field, currentSource.get(field));
                }
            }
        }
        next.setRuntimeConfigJson(JsonSupport.toJSON(
                A2uiImmutableJsonSupport.canonicalize(nextSource)));
        return next;
    }

    private List<String> componentCodes(Object value) {
        if (!(value instanceof List<?> values) || values.isEmpty()) {
            throw new A2uiRegistryValidationException(ERROR_MEMBERSHIP_INVALID);
        }
        LinkedHashSet<String> codes = new LinkedHashSet<>();
        for (Object item : values) {
            String code = item == null ? null : StringUtils.trimToNull(String.valueOf(item));
            if (code == null || !codes.add(code)) {
                throw new A2uiRegistryValidationException(ERROR_MEMBERSHIP_INVALID);
            }
        }
        return codes.stream().sorted().collect(Collectors.toList());
    }

    private String text(Map<String, Object> source, String field) {
        if (source == null) {
            return null;
        }
        Object value = source.get(field);
        return value == null ? null : StringUtils.trimToNull(String.valueOf(value));
    }

    private Long parseId(String id) {
        try {
            return Long.valueOf(id);
        } catch (RuntimeException exception) {
            throw new A2uiRegistryValidationException(ERROR_ID_INVALID);
        }
    }
}
