package dev.a2flow.management.a2ui.registry;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.registry.A2uiRegistryModels.A2uiAtomPayload;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository.ComponentAssetQuery;

import lombok.extern.slf4j.Slf4j;

/**
 * A2UI_ATOM Registry contract 转换和输入校验服务。
 *
 * <p>上游是 M 端 atom authoring 请求，下游是共享 `skill_component_registry` 领域对象。该服务
 * 负责 canonical contract、A2UI 专用列映射和通过 Repository 的当前行读写，不负责 Catalog 发布、
 * frontend support 证据或 renderer artifact。
 */
@Service
@Slf4j
public class A2uiAtomRegistryService {

    private static final String ASSET_TYPE_A2UI_ATOM = "A2UI_ATOM";
    private static final String COMPOSITION_ATOMIC = "ATOMIC";
    private static final String ERROR_PAYLOAD_REQUIRED = "A2UI_ATOM_PAYLOAD_REQUIRED";
    private static final String ERROR_REQUIRED_FIELD = "A2UI_ATOM_REQUIRED_FIELD_MISSING";
    private static final String ERROR_ATOMIC_REQUIRED = "A2UI_ATOM_MUST_BE_ATOMIC";
    private static final String ERROR_SCHEMA_INVALID = "A2UI_ATOM_SCHEMA_INVALID";
    private static final String ERROR_AUTHORITY_FORBIDDEN = "A2UI_ATOM_AUTHORITY_INPUT_FORBIDDEN";
    private static final String ERROR_ID_INVALID = "A2UI_ATOM_ID_INVALID";
    private static final String ERROR_NOT_FOUND = "A2UI_ATOM_NOT_FOUND";
    private static final String ERROR_DUPLICATE = "A2UI_ATOM_DUPLICATE";
    private static final String PARAM_KEYWORD = "keyword";
    private static final List<String> AUTHORITY_FIELDS = Arrays.asList(
            "lifecycle", "frontendSupport", "catalogId", "catalogRevision", "catalogDigest",
            "hostProfile", "rendererArtifactDigest", "componentOriginType", "editable", "readOnly");

    @Resource
    private SkillFactoryComponentAssetRepository assetRepository;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    /**
     * 把已校验 atom contract 映射为共享 Registry 当前行。
     */
    public ComponentAsset toRegistryAsset(A2uiAtomPayload payload, String operator) {
        validate(payload);
        Map<String, Object> contract = contractMap(payload);
        String canonicalJson = A2uiRegistryCanonicalJson.json(contract);
        return new ComponentAsset()
                .setAssetType(ASSET_TYPE_A2UI_ATOM)
                .setComponentName(payload.getComponentCode().trim())
                .setComponentNameCn(payload.getNameCn().trim())
                .setA2uiComponentType(payload.getType().trim())
                .setA2uiContractJson(canonicalJson)
                .setProtocolVersion(1)
                .setEnabled(Boolean.TRUE)
                .setOperator(StringUtils.trimToNull(operator));
    }

    /**
     * 解析 M 请求中的 atom payload，并在结构化转换前拒绝旧生命周期/支持权威字段。
     */
    public A2uiAtomPayload parsePayload(Map<String, Object> input) {
        if (input == null) {
            throw new A2uiRegistryValidationException(ERROR_PAYLOAD_REQUIRED);
        }
        for (String authorityField : AUTHORITY_FIELDS) {
            if (input.containsKey(authorityField)) {
                throw new A2uiRegistryValidationException(ERROR_AUTHORITY_FORBIDDEN);
            }
        }
        A2uiAtomPayload payload = JsonSupport.fromJSON(
                JsonSupport.toJSON(input), A2uiAtomPayload.class);
        payload.setComponentOriginType(A2uiComponentOriginType.PLATFORM_CUSTOM);
        validate(payload);
        return payload;
    }

    /** 查询 A2UI_ATOM 当前 Registry 行。 */
    public List<ComponentAsset> list(Map<String, String> params) {
        String keyword = params == null ? null : params.get(PARAM_KEYWORD);
        List<ComponentAsset> assets = assetRepository.list(new ComponentAssetQuery()
                .setAssetType(ASSET_TYPE_A2UI_ATOM)
                .setKeyword(keyword), false);
        List<ComponentAsset> result = new ArrayList<>();
        if (assets != null) {
            for (ComponentAsset asset : assets) {
                if (isVisibleAtom(asset)) {
                    result.add(asset);
                }
            }
        }
        return result;
    }

    /** 按 Registry 主键读取 A2UI_ATOM。 */
    public ComponentAsset detail(String id) {
        ComponentAsset asset = assetRepository.get(parseId(id));
        if (!isVisibleAtom(asset)) {
            throw new A2uiRegistryValidationException(ERROR_NOT_FOUND);
        }
        return asset;
    }

    /** 创建 A2UI_ATOM 当前 Registry 行；唯一性由共享 Registry 身份校验。 */
    public ComponentAsset create(String operator, Map<String, Object> input) {
        A2uiAtomPayload payload = parsePayload(input);
        if (assetRepository.existsComponentIdentity(null, ASSET_TYPE_A2UI_ATOM,
                payload.getComponentCode())) {
            throw new A2uiRegistryValidationException(ERROR_DUPLICATE);
        }
        ComponentAsset saved = assetRepository.save(toRegistryAsset(payload, operator));
        if (assetAuthorizationService != null) {
            assetAuthorizationService.initializeOwners(operator, ReleaseAssetType.A2UI_ATOM,
                    payload.getComponentCode(), null);
        }
        log.info("A2UI_ATOM Registry 创建完成, componentCode:{}, operator:{}",
                payload.getComponentCode(), operator);
        return saved;
    }

    /** 更新 A2UI_ATOM 当前 Registry 行；不接收生命周期或 support authority。 */
    public ComponentAsset update(String operator, String id, Map<String, Object> input) {
        Long assetId = parseId(id);
        ComponentAsset current = assetRepository.get(assetId);
        if (!isKuaishouCustom(current)) {
            throw new A2uiRegistryValidationException(ERROR_NOT_FOUND);
        }
        A2uiAtomPayload payload = parsePayload(input);
        if (assetRepository.existsComponentIdentity(assetId, ASSET_TYPE_A2UI_ATOM,
                payload.getComponentCode())) {
            throw new A2uiRegistryValidationException(ERROR_DUPLICATE);
        }
        ComponentAsset next = toRegistryAsset(payload, operator).setId(assetId);
        ComponentAsset updated = assetRepository.update(next);
        log.info("A2UI_ATOM Registry 更新完成, id:{}, componentCode:{}, operator:{}",
                assetId, payload.getComponentCode(), operator);
        return updated;
    }

    private void validate(A2uiAtomPayload payload) {
        if (payload == null) {
            throw new A2uiRegistryValidationException(ERROR_PAYLOAD_REQUIRED);
        }
        if (StringUtils.isAnyBlank(payload.getComponentCode(), payload.getType(), payload.getNameCn(),
                payload.getCategory(), payload.getCompositionKind())) {
            throw new A2uiRegistryValidationException(ERROR_REQUIRED_FIELD);
        }
        if (!COMPOSITION_ATOMIC.equals(payload.getCompositionKind())) {
            throw new A2uiRegistryValidationException(ERROR_ATOMIC_REQUIRED);
        }
        if (!isObjectSchema(payload.getPropsSchema()) || !isObjectSchema(payload.getEventSchema())
                || payload.getChildrenConstraint() == null || payload.getValidMessageExample() == null
                || payload.getInvalidMessageExample() == null) {
            throw new A2uiRegistryValidationException(ERROR_SCHEMA_INVALID);
        }
    }

    private boolean isObjectSchema(Map<String, Object> schema) {
        return schema != null && "object".equals(schema.get("type"));
    }

    private Map<String, Object> contractMap(A2uiAtomPayload payload) {
        Map<String, Object> contract = new LinkedHashMap<>();
        contract.put("componentCode", payload.getComponentCode().trim());
        contract.put("type", payload.getType().trim());
        contract.put("componentOriginType", origin(payload).name());
        contract.put("nameCn", payload.getNameCn().trim());
        contract.put("category", payload.getCategory().trim());
        contract.put("compositionKind", payload.getCompositionKind().trim());
        contract.put("propsSchema", payload.getPropsSchema());
        contract.put("eventSchema", payload.getEventSchema());
        contract.put("childrenConstraint", payload.getChildrenConstraint());
        contract.put("validMessageExample", payload.getValidMessageExample());
        contract.put("invalidMessageExample", payload.getInvalidMessageExample());
        return contract;
    }

    private A2uiComponentOriginType origin(A2uiAtomPayload payload) {
        return payload.getComponentOriginType() == null
                ? A2uiComponentOriginType.PLATFORM_CUSTOM : payload.getComponentOriginType();
    }

    private boolean isKuaishouCustom(ComponentAsset asset) {
        Map<String, Object> contract = asset == null ? null : asset.getA2uiContract();
        return asset != null
                && ASSET_TYPE_A2UI_ATOM.equals(asset.getAssetType())
                && contract != null
                && A2uiComponentOriginType.PLATFORM_CUSTOM.name().equals(
                contract.get("componentOriginType"));
    }

    private boolean isVisibleAtom(ComponentAsset asset) {
        Map<String, Object> contract = asset == null ? null : asset.getA2uiContract();
        if (asset == null || !ASSET_TYPE_A2UI_ATOM.equals(asset.getAssetType())
                || contract == null) {
            return false;
        }
        try {
            A2uiComponentOriginType.parse(String.valueOf(contract.get("componentOriginType")));
            return true;
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private Long parseId(String id) {
        try {
            return Long.valueOf(id);
        } catch (Exception exception) {
            throw new A2uiRegistryValidationException(ERROR_ID_INVALID);
        }
    }
}
