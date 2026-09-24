package dev.a2flow.management.release;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application.A2uiImmutableJsonSupport;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogSourceType;
import dev.a2flow.management.a2ui.registry.A2uiComponentOriginType;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.GateResult;
import dev.a2flow.management.release.ReleaseModels.PublishResult;
import dev.a2flow.management.release.ReleaseModels.ReleasePublishContext;
import dev.a2flow.management.release.ReleaseModels.ReleaseValidationRequirement;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository.ComponentAssetQuery;

import lombok.extern.slf4j.Slf4j;

/**
 * A2UI Catalog 独立发布适配器。
 *
 * <p>上游是共享 release control plane，下游是 A2UI_ATOM Registry 当前行集合。该适配器只组装
 * Catalog canonical snapshot，不复用旧 COMPONENT 生命周期，也不要求额外 Renderer/support 证据。
 */
@Component
@Slf4j
public class A2uiCatalogReleaseAssetAdapter extends AbstractReleaseAssetAdapter {

    private static final String ASSET_TYPE = "A2UI_CATALOG";
    private static final String ATOM_ASSET_TYPE = "A2UI_ATOM";
    private static final String PROTOCOL_VERSION = "v0.9.1";
    private static final String GATE_ATOMS = "A2UI_CATALOG_ATOMS";
    private static final String LABEL_ATOMS = "A2UI 原子组件集合";
    private static final String MESSAGE_ATOMS_READY = "A2UI 原子组件集合已冻结";
    private static final String MESSAGE_ATOMS_MISSING = "A2UI 原子组件集合为空";
    private static final String ERROR_SOURCE_REQUIRED = "A2UI_CATALOG_SOURCE_REQUIRED";
    private static final String ERROR_SOURCE_INVALID = "A2UI_CATALOG_SOURCE_INVALID";
    private static final String ERROR_MEMBERSHIP_INVALID = "A2UI_CATALOG_MEMBERSHIP_INVALID";

    @Resource
    private SkillFactoryComponentAssetRepository assetRepository;

    @Override
    public ReleaseAssetType assetType() {
        return ReleaseAssetType.A2UI_CATALOG;
    }

    @Override
    public AssetSnapshot currentSnapshot(String assetKey, Map<String, String> params) {
        if (assetRepository == null || StringUtils.isBlank(assetKey)) {
            throw new IllegalStateException(ERROR_SOURCE_REQUIRED);
        }
        ComponentAsset catalogAsset = assetRepository.findByAssetTypeAndName(ASSET_TYPE, assetKey);
        Map<String, Object> catalogSource = catalogSource(catalogAsset, assetKey);
        List<String> componentCodes = componentCodes(catalogSource);
        List<ComponentAsset> atoms = assetRepository.list(
                new ComponentAssetQuery().setAssetType(ATOM_ASSET_TYPE), true);
        if (atoms == null || atoms.isEmpty()) {
            throw new IllegalStateException(ERROR_SOURCE_REQUIRED);
        }
        List<Map<String, Object>> components = new ArrayList<>();
        Map<String, ComponentAsset> atomByCode = new LinkedHashMap<>();
        for (ComponentAsset atom : atoms) {
            if (atom != null && StringUtils.isNotBlank(atom.getComponentName())) {
                if (atomByCode.put(atom.getComponentName(), atom) != null) {
                    throw new IllegalStateException(ERROR_MEMBERSHIP_INVALID);
                }
            }
        }
        for (String componentCode : componentCodes) {
            ComponentAsset atom = atomByCode.get(componentCode);
            if (atom == null || StringUtils.isBlank(atom.getComponentName())
                    || StringUtils.isBlank(atom.getA2uiComponentType())
                    || atom.getA2uiContract() == null) {
                throw new IllegalStateException(ERROR_MEMBERSHIP_INVALID);
            }
            String origin = String.valueOf(atom.getA2uiContract().get("componentOriginType"));
            A2uiComponentOriginType originType = A2uiComponentOriginType.parse(origin);
            if (originType != A2uiComponentOriginType.PLATFORM_CUSTOM
                    && originType != A2uiComponentOriginType.A2UI_OFFICIAL) {
                throw new IllegalStateException(ERROR_MEMBERSHIP_INVALID);
            }
            Map<String, Object> component = new LinkedHashMap<>();
            component.put("componentCode", atom.getComponentName());
            component.put("type", atom.getA2uiComponentType());
            component.put("componentOriginType", origin);
            component.put("nameCn", atom.getComponentNameCn());
            component.put("contract", atom.getA2uiContract());
            components.add(component);
        }
        components.sort(Comparator.comparing(value -> String.valueOf(value.get("componentCode"))));
        Map<String, Object> catalog = new LinkedHashMap<>(catalogSource);
        catalog.remove("componentCodes");
        catalog.put("components", components);
        Object canonicalCatalog = A2uiImmutableJsonSupport.canonicalize(catalog);
        String payloadJson = JsonSupport.toJSON(canonicalCatalog);
        String digest = "sha256:" + ReleaseDigestUtils.sha256(payloadJson);
        return new AssetSnapshot()
                .setAssetType(ASSET_TYPE)
                .setAssetKey(assetKey)
                .setDigest(digest)
                .setSummary(summaryEntry("catalogId", assetKey, "componentCount", components.size()))
                .setPayloadJson(payloadJson);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> catalogSource(ComponentAsset asset, String assetKey) {
        if (asset == null || StringUtils.isBlank(asset.getRuntimeConfigJson())) {
            throw new IllegalStateException(ERROR_SOURCE_REQUIRED);
        }
        Object value = JsonSupport.fromJSON(asset.getRuntimeConfigJson(), Object.class);
        if (!(value instanceof Map)) {
            throw new IllegalStateException(ERROR_SOURCE_INVALID);
        }
        Map<String, Object> source = (Map<String, Object>) value;
        if (!assetKey.equals(source.get("catalogId"))
                || !PROTOCOL_VERSION.equals(source.get("protocolVersion"))) {
            throw new IllegalStateException(ERROR_SOURCE_INVALID);
        }
        if (A2uiCatalogSourceType.parse(String.valueOf(source.get("catalogSourceType")))
                != A2uiCatalogSourceType.PLATFORM_MANAGED) {
            throw new IllegalStateException(ERROR_SOURCE_INVALID);
        }
        return source;
    }

    private List<String> componentCodes(Map<String, Object> source) {
        Object value = source.get("componentCodes");
        if (!(value instanceof List<?> values) || values.isEmpty()) {
            throw new IllegalStateException(ERROR_MEMBERSHIP_INVALID);
        }
        List<String> codes = new ArrayList<>();
        for (Object item : values) {
            String code = item == null ? null : StringUtils.trimToNull(String.valueOf(item));
            if (code == null || codes.contains(code)) {
                throw new IllegalStateException(ERROR_MEMBERSHIP_INVALID);
            }
            codes.add(code);
        }
        return codes;
    }

    @Override
    public List<GateResult> evaluateGates(String assetKey, ReleaseEnvironment environment,
            AssetSnapshot snapshot, Map<String, String> params) {
        boolean ready = snapshot != null && StringUtils.isNotBlank(snapshot.getPayloadJson());
        return List.of(gate(GATE_ATOMS, LABEL_ATOMS, ready, true,
                ready ? MESSAGE_ATOMS_READY : MESSAGE_ATOMS_MISSING));
    }

    @Override
    public List<ReleaseValidationRequirement> validationRequirements(ReleaseEnvironment environment) {
        return List.of();
    }

    @Override
    public void restore(String userName, String assetKey, AssetSnapshot snapshot,
            Map<String, String> params) {
        throw new IllegalStateException("A2UI Catalog historical restore is not connected");
    }

    @Override
    public boolean supportsPublishingRecovery() {
        return true;
    }

    @Override
    public PublishResult deploy(ReleasePublishContext context) {
        AssetSnapshot snapshot = context == null ? null : context.getSnapshot();
        if (snapshot == null || StringUtils.isBlank(snapshot.getPayloadJson())) {
            return failed("A2UI Catalog immutable snapshot is required");
        }
        log.info("A2UI Catalog immutable snapshot 发布完成, assetKey:{}, environment:{}, operator:{}",
                context.getAssetKey(), context.getEnvironment(), context.getUserName());
        return succeeded("A2UI Catalog immutable snapshot 发布完成", summaryEntry(
                "assetKey", context.getAssetKey(), "digest", snapshot.getDigest()));
    }
}
