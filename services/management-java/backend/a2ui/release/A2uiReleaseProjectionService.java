package dev.a2flow.management.a2ui.release;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogSourceType;
import dev.a2flow.management.a2ui.registry.A2uiRegistryValidationException;
import dev.a2flow.management.release.PublishedAssetQueryService;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.PublishedAssetSnapshot;

import lombok.extern.slf4j.Slf4j;

/**
 * A2UI M 端只读发布投影服务。
 *
 * <p>上游是共享 PRT/ONLINE 环境指针，下游是 Catalog/Application 管理页。该服务只投影
 * 精确环境版本与 Catalog 成员，不接受客户端 release authority，不读取 support/Profile/Renderer
 * 证据，也不把缺失环境回退到另一环境、latest 或 Registry 当前值。
 */
@Service
@Slf4j
public class A2uiReleaseProjectionService {

    private static final String FIELD_STATUS = "status";
    private static final String FIELD_VERSION = "version";
    private static final String FIELD_MATCHES_CURRENT_SOURCE = "matchesCurrentSource";
    private static final String FIELD_HAS_UNPUBLISHED_CHANGES = "hasUnpublishedChanges";
    private static final String STATUS_DRAFT = "DRAFT";
    private static final String PROTOCOL_VERSION = "v0.9.1";
    private static final String FIELD_CATALOG_ID = "catalogId";
    private static final String FIELD_CATALOG_SOURCE_TYPE = "catalogSourceType";
    private static final String FIELD_PROTOCOL_VERSION = "protocolVersion";
    private static final String FIELD_COMPONENTS = "components";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_COMPONENT_ORIGIN_TYPE = "componentOriginType";
    private static final String FIELD_CATALOG = "catalog";
    private static final String FIELD_RELEASES = "releases";
    private static final String FIELD_RELEASE_BLOCKERS = "releaseBlockers";
    private static final String FIELD_REVISION = "revision";
    private static final String FIELD_DIGEST = "digest";
    private static final String FIELD_ENABLED = "enabled";
    private static final String FIELD_COMPONENT_TYPES = "componentTypes";
    private static final String FIELD_COMPONENT_ORIGINS = "componentOrigins";
    private static final String ERROR_CATALOG_ID_REQUIRED = "A2UI_APPLICATION_CATALOG_ID_REQUIRED";
    private static final String ERROR_CATALOG_INVALID = "A2UI_APPLICATION_CATALOG_INVALID";
    private static final String BLOCKER_PREPROD = "A2UI_APPLICATION_CATALOG_PREPROD_NOT_PUBLISHED";
    private static final String BLOCKER_ONLINE = "A2UI_APPLICATION_CATALOG_ONLINE_NOT_PUBLISHED";

    @Resource
    private PublishedAssetQueryService publishedAssetQueryService;

    /**
     * 按 Application current source 的 exact catalogId 生成管理面依赖投影。
     *
     * <p>PRT 和 ONLINE 独立投影；缺失环境只形成服务端 blocker，不阻止草稿查看与编辑。
     */
    public Map<String, Object> applicationDependencyProjection(String catalogId) {
        if (StringUtils.isBlank(catalogId)) {
            throw failure(ERROR_CATALOG_ID_REQUIRED, catalogId);
        }
        Map<ReleaseEnvironment, PublishedAssetSnapshot> published = publishedCatalog(catalogId);
        PublishedAssetSnapshot preprod = published.get(ReleaseEnvironment.PRT);
        PublishedAssetSnapshot online = published.get(ReleaseEnvironment.ONLINE);
        PublishedAssetSnapshot metadataSource = preprod == null ? online : preprod;

        Map<String, Object> catalog = catalogMetadata(catalogId, metadataSource);
        catalog.put(FIELD_RELEASES, releaseSummaries(preprod, online));
        List<String> blockers = new ArrayList<>();
        if (preprod == null) {
            blockers.add(BLOCKER_PREPROD);
        }
        if (online == null) {
            blockers.add(BLOCKER_ONLINE);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_CATALOG, catalog);
        result.put(FIELD_RELEASE_BLOCKERS, blockers);
        log.info("A2UI Application环境依赖投影完成, catalogId:{}, preprod:{}, online:{}",
                catalogId, preprod != null, online != null);
        return result;
    }

    /** 返回 Catalog PRT/ONLINE 精确版本的服务端只读投影。 */
    public Map<String, Object> catalogProjection(String catalogKey) {
        if (StringUtils.isBlank(catalogKey)) {
            throw failure(ERROR_CATALOG_ID_REQUIRED, catalogKey);
        }
        Map<ReleaseEnvironment, PublishedAssetSnapshot> published = publishedCatalog(catalogKey);
        PublishedAssetSnapshot preprod = published.get(ReleaseEnvironment.PRT);
        PublishedAssetSnapshot online = published.get(ReleaseEnvironment.ONLINE);
        Map<String, Object> result = catalogMetadata(catalogKey, preprod == null ? online : preprod);
        result.put(FIELD_RELEASES, releaseSummaries(preprod, online));
        Map<String, Object> onlineSummary = releaseSummary(online);
        result.put(FIELD_REVISION, onlineSummary.get(FIELD_REVISION));
        result.put(FIELD_DIGEST, onlineSummary.get(FIELD_DIGEST));
        result.put(FIELD_ENABLED, onlineSummary.get(FIELD_ENABLED));
        return result;
    }

    private Map<ReleaseEnvironment, PublishedAssetSnapshot> publishedCatalog(String catalogId) {
        try {
            return publishedAssetQueryService.publishedEnvironments(ReleaseAssetType.A2UI_CATALOG, catalogId);
        } catch (RuntimeException exception) {
            return Map.of();
        }
    }

    /** Application 自身的发布状态与源内容差异；不使用 Catalog 发布状态替代应用发布事实。 */
    public Map<String, Object> applicationProjection(String appCode, String sourceDigest) {
        Map<ReleaseEnvironment, PublishedAssetSnapshot> published =
                publishedAssetQueryService.publishedEnvironments(ReleaseAssetType.A2UI_APPLICATION, appCode);
        PublishedAssetSnapshot online = published.get(ReleaseEnvironment.ONLINE);
        PublishedAssetSnapshot preprod = published.get(ReleaseEnvironment.PRT);
        Map<String, Object> releases = new LinkedHashMap<>();
        for (ReleaseEnvironment environment : ReleaseEnvironment.values()) {
            PublishedAssetSnapshot snapshot = published.get(environment);
            Map<String, Object> summary = releaseSummary(snapshot);
            summary.put(FIELD_VERSION, snapshot == null ? null : snapshot.getVersion());
            summary.put(FIELD_MATCHES_CURRENT_SOURCE, matchesCurrentSource(snapshot, sourceDigest));
            releases.put(environment.name(), summary);
        }
        PublishedAssetSnapshot comparison = online == null ? preprod : online;
        Boolean matches = matchesCurrentSource(comparison, sourceDigest);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_STATUS, online != null ? ReleaseEnvironment.ONLINE.name()
                : preprod != null ? ReleaseEnvironment.PRT.name() : STATUS_DRAFT);
        result.put(FIELD_RELEASES, releases);
        // 历史产物缺少 inputDigest 时无法判断差异，不把未知伪装成已同步或有修改。
        result.put(FIELD_HAS_UNPUBLISHED_CHANGES, matches == null ? null : !matches);
        return result;
    }

    private Boolean matchesCurrentSource(PublishedAssetSnapshot snapshot, String sourceDigest) {
        return snapshot == null || StringUtils.isBlank(snapshot.getInputDigest())
                ? null : StringUtils.equals(sourceDigest, snapshot.getInputDigest());
    }

    private Map<String, Object> releaseSummaries(
            PublishedAssetSnapshot preprod, PublishedAssetSnapshot online) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(ReleaseEnvironment.PRT.name(), releaseSummary(preprod));
        result.put(ReleaseEnvironment.ONLINE.name(), releaseSummary(online));
        return result;
    }

    private Map<String, Object> releaseSummary(PublishedAssetSnapshot published) {
        AssetSnapshot snapshot = published == null ? null : published.getSnapshot();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_REVISION,
                published == null ? "" : StringUtils.defaultString(published.getVersionId()));
        result.put(FIELD_DIGEST,
                snapshot == null ? "" : StringUtils.defaultString(snapshot.getDigest()));
        result.put(FIELD_ENABLED, published != null && snapshot != null);
        return result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> catalogMetadata(
            String catalogId, PublishedAssetSnapshot published) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_CATALOG_ID, catalogId);
        result.put(FIELD_CATALOG_SOURCE_TYPE, "");
        result.put(FIELD_PROTOCOL_VERSION, PROTOCOL_VERSION);
        result.put(FIELD_COMPONENT_TYPES, List.of());
        result.put(FIELD_COMPONENT_ORIGINS, Map.of());
        if (published == null || published.getSnapshot() == null) {
            return result;
        }
        AssetSnapshot snapshot = published.getSnapshot();
        Map<String, Object> payload;
        try {
            payload = JsonSupport.fromJSON(snapshot.getPayloadJson(), Map.class);
        } catch (RuntimeException exception) {
            throw failure(ERROR_CATALOG_INVALID, catalogId);
        }
        if (payload == null
                || !StringUtils.equals(catalogId, published.getAssetKey())
                || !StringUtils.equals(catalogId, snapshot.getAssetKey())
                || !StringUtils.equals(catalogId, String.valueOf(payload.get(FIELD_CATALOG_ID)))
                || !PROTOCOL_VERSION.equals(payload.get(FIELD_PROTOCOL_VERSION))) {
            throw failure(ERROR_CATALOG_INVALID, catalogId);
        }
        String sourceType = String.valueOf(payload.get(FIELD_CATALOG_SOURCE_TYPE));
        try {
            if (A2uiCatalogSourceType.parse(sourceType)
                    != A2uiCatalogSourceType.PLATFORM_MANAGED) {
                throw failure(ERROR_CATALOG_INVALID, catalogId);
            }
        } catch (A2uiRegistryValidationException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw failure(ERROR_CATALOG_INVALID, catalogId);
        }
        Object componentsValue = payload.get(FIELD_COMPONENTS);
        if (!(componentsValue instanceof List)) {
            throw failure(ERROR_CATALOG_INVALID, catalogId);
        }
        List<String> componentTypes = new ArrayList<>();
        Map<String, String> componentOrigins = new LinkedHashMap<>();
        for (Object value : (List<Object>) componentsValue) {
            if (!(value instanceof Map)) {
                throw failure(ERROR_CATALOG_INVALID, catalogId);
            }
            Map<String, Object> component = (Map<String, Object>) value;
            String type = String.valueOf(component.get(FIELD_TYPE));
            String origin = String.valueOf(component.get(FIELD_COMPONENT_ORIGIN_TYPE));
            if (StringUtils.isAnyBlank(type, origin)
                    || componentOrigins.putIfAbsent(type, origin) != null) {
                throw failure(ERROR_CATALOG_INVALID, catalogId);
            }
            componentTypes.add(type);
        }
        result.put(FIELD_CATALOG_SOURCE_TYPE, sourceType);
        result.put(FIELD_COMPONENT_TYPES, componentTypes);
        result.put(FIELD_COMPONENT_ORIGINS, componentOrigins);
        return result;
    }

    private A2uiRegistryValidationException failure(String errorCode, String catalogId) {
        log.warn("A2UI Catalog环境投影失败, catalogId:{}, errorCode:{}", catalogId, errorCode);
        return new A2uiRegistryValidationException(errorCode);
    }
}
